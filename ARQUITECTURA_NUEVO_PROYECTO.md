# Arquitectura — bff-manager-admin

Cómo está construido este BFF, por qué, y las convenciones que toda feature nueva debe seguir. `features/employee` es la implementación de referencia: ante la duda, se copia su forma.

## 1. Qué es este proyecto

BFF en **FastAPI + SQLAlchemy 2.0** para las herramientas de manager/admin. Lee y escribe directamente sobre la misma base Postgres que usa `manage-admin-api` (NestJS/TypeORM) para las tablas `employee_*`. No es un wrapper de la API REST de `manage-admin-api`: es el mismo rol que cumple `bff-lsg-placement` con su propia base.

El objetivo inmediato es reemplazar las queries escritas a mano en Retool por endpoints con contrato documentado (OpenAPI), validación y transacciones.

## 2. De dónde viene este diseño

El diseño parte de lo aprendido en `bff-lsg-placement`, que usaba solo **SQLAlchemy Core** (`Table` + `select()`/`insert()` manuales):

- **Cada relación nueva costaba ~15 ediciones de archivos**: schema, port, repositorio, use cases, subconsultas `array_agg` a mano, filtros, controller y tests. Todo eso para una relación 1-a-muchos genérica.
- **El "GET anidado" siempre se escribía a mano**, con `array_agg`/`JSON_AGG` o fetch-y-merge en Python.
- **Los Fakes de test reimplementaban lógica** y se desincronizaban del repositorio real.
- **Cada feature reinventó la paginación, los filtros y la forma de respuesta**, y terminaron divergiendo: `order_by` vs `sort` en el mismo archivo, cuatro defaults distintos de `per_page` y respuestas paginadas armadas a mano sin `response_model`.
- **Se crearon tablas en la base sin migración ni `GRANT` coordinado**, y eso tumbó producción.

Se preservó lo que sí funcionaba: separación por feature, bulk con savepoint por ítem (best-effort), manejador global de errores (`AppError`), lista blanca de identificadores en SQL dinámico, `merge_query_filters`.

## 3. Dos tracks de acceso a datos

### Track A — ORM declarativo (lo que usa `employee`)

Para todo lo que sea "dame o edita esta entidad y sus hijos". Las relaciones se declaran **una sola vez** en `models.py`:

```python
class EmployeePerson(Base):
    __tablename__ = "employee_persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roles: Mapped[List["EmployeeRole"]] = relationship(back_populates="person", lazy="raise")
    technologies: Mapped[List["EmployeeTechnology"]] = relationship(back_populates="person", lazy="raise")
```

`lazy="raise"` es obligatorio en toda relación: si alguna se accede sin haberla cargado explícitamente, falla en lugar de disparar un N+1 silencioso. Es el equivalente a que Prisma obligue a escribir `include`. Con esto, el detalle completo de un empleado, que en Retool eran 7 queries, es **una sola** query con `selectinload` (`EmployeeRepository.get_person_detail`).

### Track B — SQL propio (archivos `.sql`)

Para lecturas que el ORM no expresa bien en una sola query: `string_agg`/`json_agg`, `LATERAL`, `DISTINCT ON`, funciones de ventana, CTEs, pivots y reportes. El SQL va en un archivo `.sql` dentro de la feature y lo ejecuta su `custom_repository.py` (ver "SQL propio" en la sección 5). Caso actual: `employee/sql/person_summary.sql`.

Una vista que solo **resuelve nombres** con joins (ids de catálogo → `name`) no necesita `.sql`: es un `select()` con `outerjoin` a las tablas de `catalogs/tables.py` en `repository.py`, que genera el mismo SQL en una sola query. Caso actual: `EmployeeRepository.get_person_positions`, que antes era un `.sql` y se pasó al ORM con resultado idéntico (300/300 personas contra la BD real) y el mismo tiempo.

**Regla de decisión**:
- ¿"Dame esta entidad con sus relaciones, para **editarla**"? → **Track A** (ORM).
- ¿Listado genérico o catálogo? → `BaseRepository` / Core.
- ¿Vista de solo lectura que solo resuelve nombres con joins? → `select()` + `outerjoin` en `repository.py`.
- ¿Vista con agregados por fila (`json_agg`, `string_agg`), `LATERAL`, ventanas o reportes? → **Track B** (`.sql`).

## 4. Estructura del proyecto

```
app/
  main.py                 # FastAPI app, handlers globales de errores, CORS, middleware
  config.py               # variables de entorno
  api/v1.py               # router /v1 - incluye el router de cada feature
  infrastructure/
    database.py           # engine, SessionLocal, Base (DeclarativeBase), get_db
  shared/
    errors.py             # AppError, NotFoundError, ConflictError, InvalidFieldError, get_or_404
    responses.py          # Page[T], Envelope[T], BulkResponse
    pagination.py         # pagination_params(), sort_params() - fábricas de Depends
    query_filters.py      # merge_query_filters
    repository.py         # BaseRepository - CRUD genérico + bulk best-effort
    sql.py                # load_sql, fetch_one, fetch_all, fetch_page - para los .sql
    projection.py         # parse_fields (portado, aún sin usar - ver sección 9)
    permissions.py        # check_permission (stub - no hay auth todavía)
    middleware.py         # RequestTimingMiddleware (log de método, ruta, status, duración)
  features/
    catalogs/
      tables.py           # Tables Core de los general_* (generadas del esquema real)
      registry.py         # CATALOGS: nombre -> tabla + orden + relaciones + filtro fijo
      repository.py       # CatalogRepository(BaseRepository) - consulta genérica
      use_cases/query.py  # get_catalogs: batch best-effort + expansión de relaciones
      schemas/            # CatalogBatchRequest / CatalogBatchResponse
      controller.py       # POST /catalogs
    employee/
      models.py           # modelos ORM del agregado (todas sus tablas en un módulo)
      repository.py       # EmployeeRepository(BaseRepository) - ORM: agregado, escrituras, /details, /positions
      custom_repository.py # repositorio de solo lectura con SQL propio (Track B)
      sql/
        person_summary.sql    # cabecera de la vista del empleado
      use_cases/
        query.py          # funciones de lectura
        write.py          # funciones de escritura
      schemas/
        request.py        # modelos Pydantic de entrada (los "DTOs" de entrada)
        response.py       # modelos Pydantic de salida (response_model)
      controller.py       # rutas FastAPI
```

### Flujo de una request

```
ORM:                controller  →  use_cases  →  repository  →  models (ORM)  →  Postgres
SQL propio:         controller  →  custom_repository.py  →  sql/*.sql  →  Postgres
   │                   │              │
   │                   │              └─ ejecuta / hace flush, nunca commit
   │                   └─ reglas del caso de uso; convierte Pydantic → dict
   └─ valida entrada (schemas/request), inyecta repo o sesión con Depends, envuelve en Envelope/Page
```

Las vistas de solo lectura no pasan por un use case: no tienen lógica, así que solo reenviarían la llamada. Si una vista llega a necesitar lógica (combinar dos queries, reglas de negocio), se le agrega su función en `use_cases/query.py`.

**La sesión es la unidad de trabajo de la request.** `get_db` abre la sesión, hace **un solo `commit`** al final si todo salió bien y `rollback` si hubo una excepción. Ni los repositorios ni los use cases hacen commit, así que un flujo de varios pasos nunca queda aplicado a medias.

## 5. Convenciones de código

El enfoque es pragmático, no hexagonal estricto. El dominio **son** los modelos ORM del Track A, así que no hay ports/ABCs: con una sola implementación (SQLAlchemy) y el dominio ya acoplado al ORM, una interfaz no aislaría nada y solo duplicaría firmas.

### Organización
- **Un módulo agrupa lo que cambia junto.** En Python la unidad es el módulo, no la clase, así que tener varias clases por archivo es lo normal (a diferencia de la convención "una clase por archivo" de Java/TS). Si un módulo pasa de ~400–500 líneas, se convierte en paquete (`models/__init__.py` re-exportando) sin romper imports.
- **`schemas/` para Pydantic, `models.py` para ORM.** No se mezclan: `models` describe la tabla y `schemas` describe el contrato HTTP.

### Repositorios
- **Uno por agregado, no por tabla**, heredando de `shared/repository.py::BaseRepository`. `EmployeeRepository` cubre `employee_persons` y todas sus tablas hijas.
- La feature **solo escribe las consultas con forma propia**: listado filtrado, detalle con `selectinload`. Todo lo demás viene de la base, que recibe el modelo como parámetro:

| Tipo | Métodos de `BaseRepository` |
|---|---|
| Lectura | `get`, `get_many(ids)`, `find_by(**igualdades)`, `exists` |
| Escritura de una fila | `create`, `update`, `update_by_id` (lanza `NotFoundError`), `delete` |
| Escritura masiva | `create_many`, `update_many`, `upsert_many(required_on_create=...)`, `delete_many` |
| Transacción | `savepoint` (para loops best-effort propios) |

- **Bulk best-effort**: `create_many`, `update_many` y `upsert_many` ejecutan cada ítem en su propio SAVEPOINT. Si un ítem falla, solo ese se revierte. Todos devuelven `[{"index", "ok", "id"}]` o `[{"index", "ok", "error"}]`, y el controller responde `{"ok": all(...), "results": [...]}`.
- **`delete_many` es todo o nada** (una sola sentencia `DELETE ... WHERE id IN (...)`).
- `create`/`update` asignan `created_at`/`updated_at` con el `now` que reciben del use case.
- Una sola capa de herencia; la base no lleva lógica de negocio.

### Use cases
- **Funciones, no clases.** Una clase con solo `__init__` + `execute` es una función con pasos de más. Reciben el repositorio como primer parámetro: `write.delete_language(repo, language_row_id)`.
- Convierten el Pydantic a dict (`model_dump(exclude_none=True)`) y delegan al repositorio. Cuando el caso es genérico, una sola función sirve para varios modelos: `write.bulk_upsert(repo, EmployeeRole, items, required_on_create=("person_id",))`.
- Una clase solo se justifica si guarda estado o tiene varios métodos con lógica real.
- Si algún día hace falta sustituir el repositorio (otra fuente de datos, un doble de test), se declara un `typing.Protocol` en ese momento, solo para ese caso.

### Endpoints de escritura: un bulk-upsert por entidad

Crear y actualizar es **un solo endpoint por entidad**: `POST /<feature>/<recurso>/bulk-upsert`, que recibe una lista (uno o muchos ítems):

- Ítem **con `id`** → actualiza esa fila. Solo cambian los campos enviados; los `null`/ausentes no se tocan.
- Ítem **sin `id`** → crea una fila. Debe traer los campos de `required_on_create` del endpoint, normalmente la FK al padre (`person_id`, `employee_role_id`, ...). Si faltan, ese ítem falla con un mensaje claro en lugar de un error de constraint de Postgres.
- **Best-effort**: cada ítem corre en su propio SAVEPOINT. La respuesta es `BulkResponse` (`shared/responses.py`):
  ```json
  {"ok": false, "results": [
    {"index": 0, "ok": true,  "id": 1318, "error": null},
    {"index": 1, "ok": false, "id": null, "error": "employee_languages requires person_id to be created"}
  ]}
  ```
  `ok` es `true` solo si todos los ítems salieron bien. El cliente obtiene el `id` de cada fila creada en `results`.
- **Los deletes van separados** (`DELETE`), no dentro del upsert.
- No hay endpoints de "crear uno" ni "actualizar uno": crear o actualizar una sola fila es enviar una lista de un ítem.
- El schema de entrada es uno por entidad (`XUpsertItem`), con `id` y todos los campos opcionales. La regla de qué se necesita para crear vive en `required_on_create`, en el controller.

### Controllers
- El repositorio se inyecta con una dependencia de la feature:
  ```python
  def get_repository(db: Session = Depends(get_db)) -> EmployeeRepository:
      return EmployeeRepository(db)
  ```
- **Las rutas estáticas van antes que las rutas con parámetro.** FastAPI evalúa en orden de declaración: si `PATCH /positions/{position_id}` va antes que `PATCH /positions/bulk`, `"bulk"` se captura como `position_id` y responde 422. Este bug existió en `employee`.
- Toda respuesta declara `response_model`: `Envelope[XOut]`, `Page[XOut]` o `BulkResponse`.

### Modelos y tipos
- **El tipo del modelo debe coincidir con el de la columna real en Postgres**, no con lo que diga otra fuente (Retool, TypeORM). Las columnas `numeric(p,s)` se mapean como `Mapped[Optional[Decimal]] = mapped_column(Numeric)`, entran como `Decimal` en `schemas/request.py` y salen como `float` en `schemas/response.py`, para que el JSON tenga números y no strings. Mapearlas como `int` rompió `GET /details/{id}` con `monthly_sales_price = 6114.78`.
  - Para verificar tipos: `select column_name, data_type, numeric_precision, numeric_scale from information_schema.columns where table_name = '...'`.
- **Los ids de catálogos** (`role_id`, `seniority_id`, `technology_id`, `silo_id`, `cost_center_id`, etc.) son enteros planos, sin FK ni `relationship()`. El frontend resuelve sus nombres con `POST /catalogs`.
- Solo las relaciones **dentro del agregado** se declaran como `ForeignKey` + `relationship()`.

### SQL propio: archivos `.sql` por feature

Una feature separa sus lecturas en dos archivos:

| Archivo | Para qué | Estilo |
|---|---|---|
| `repository.py` | Todo lo que el ORM expresa en una query: el agregado, escrituras, `/details`, vistas que resuelven nombres con joins (`/positions`) | ORM / `select()`, hereda de `BaseRepository` |
| `custom_repository.py` + `sql/` | Lo que el ORM no expresa bien: agregados por fila, `LATERAL`, ventanas, reportes (`/summary`) | Funciones que reciben la sesión y ejecutan un `.sql` |

La pregunta no es "¿se edita o se muestra?" sino "¿el ORM lo genera en una sola query legible?". Si sí, ORM: lo tipa el modelo y un renombre de columna rompe al importar. Si no, `.sql`.

```
features/employee/
  custom_repository.py       ← _PERSON_SUMMARY = load_sql(__file__, "person_summary")
  sql/person_summary.sql     ← SQL puro, parámetros :person_id
```

```python
# custom_repository.py
def get_person_summary(db: Session, person_id: int) -> Optional[Row]:
    return fetch_one(db, _PERSON_SUMMARY, person_id=person_id)

# controller.py - sin use case: la vista no tiene lógica
@router.get("/persons/{person_id}/summary", response_model=Envelope[EmployeePersonSummaryOut])
def get_employee_person_summary(person_id: int, db: Session = Depends(get_db)):
    summary = get_or_404(custom_repository.get_person_summary(db, person_id), detail="employee_persons not found")
    return Envelope(data=summary)
```

Helpers de `shared/sql.py`:
- `fetch_one(db, SQL, **params)` → `dict | None`; `fetch_all(db, SQL, **params)` → `list[dict]`.
- `fetch_page(db, SQL, params, page=, per_page=, sortable={...}, sort=, direction=)` → `(rows, total)`. Envuelve el `.sql` como subconsulta para el conteo y para `ORDER BY`/`LIMIT`/`OFFSET`, sin tocar el archivo. Solo ordena por columnas de `sortable` (columnas de salida del `.sql`) y desempata por `id`; cualquier otro valor es un `InvalidFieldError`. Los listados paginados y los reportes usan esto, no SQL armado a mano.

Reglas:
1. **Un archivo por query**, en `features/<feature>/sql/`. Se puede abrir con resaltado de sintaxis y pegar tal cual en DBeaver.
2. **Solo parámetros enlazados (`:param`)**, nunca f-strings ni `.format()`. Un filtro opcional se escribe en el SQL: `AND (:city_id IS NULL OR ep.city_id = :city_id)`. Paginación y orden dinámico, con `fetch_page`. Si un query necesita mucho SQL dinámico (filtros que cambian joins), va con Core y no en `.sql`.
3. **Se carga una vez, al importar** (`load_sql` a nivel de módulo), y lo ejecuta solo `custom_repository.py`.
4. **La salida pasa siempre por un `response_model`.** El contrato del endpoint lo define Pydantic, no los alias del SQL.
5. **Toda tabla que toque el `.sql` está declarada** en algún `models.py` o en `catalogs/tables.py`. Así el contenedor de tests la crea y el drift la vigila.
6. **Tests:** `tests/test_sql_files.py` ejecuta un `EXPLAIN` de todos los `.sql` contra el Postgres de test, así que un error de sintaxis o una columna inexistente falla sin escribir nada. El comportamiento se prueba por el endpoint, como cualquier otro (`test_summary.py`, `test_positions.py`).
7. Arriba de cada archivo, un comentario con **qué vista alimenta** y, si reemplaza un query de Retool, qué corrige.

**Reportes que cruzan features** (p. ej. empleados + cuentas + facturación) no pertenecen a ninguna feature: van en `features/reports/` con la misma forma (`custom_repository.py`, `sql/`, `controller.py` con prefijo `/reports`). Se crea cuando llegue el primero.

### Catálogos: un solo endpoint para todos (`POST /catalogs`)

Las tablas `general_*` se leen todas con el mismo código, sin un endpoint ni una query por catálogo. Una sola llamada trae varios catálogos sobre la misma conexión:

```json
POST /v1/catalogs
{"requests": [
  {"catalog": "seniorities"},
  {"catalog": "languages", "per_page": 500},
  {"catalog": "cities", "filters": {"country_id": 37}, "relations": "country"},
  {"catalog": "silos", "alias": "top_silos", "filters": {"report_to_silo_id": null}, "sort": "name", "direction": "desc"}
]}
```

| Campo | Default | Notas |
|---|---|---|
| `catalog` | — | Nombre de la tabla sin `general_` (`general_cities` → `cities`) |
| `alias` | `catalog` | Clave en la respuesta; sirve para pedir el mismo catálogo dos veces |
| `filters` | `{}` | Columna → valor. `null` → `IS NULL`, lista → `IN`, texto en columna de texto → contiene (sin distinguir mayúsculas), otro → igual |
| `page` / `per_page` | `1` / `20` | `per_page` máximo 500 |
| `sort` / `direction` | orden propio del catálogo / `asc` | Por defecto `order`, si no `name`, si no `id`; siempre desempata por `id` |
| `relations` | — | FKs a expandir, separadas por coma; anidadas con punto: `"report_to_silo.report_to_silo"` |

Respuesta: `{"ok": bool, "results": {"<alias o catalog>": {"ok", "data", "total", "page", "per_page"} | {"ok": false, "error"}}}`. Es **best-effort**: un catálogo inexistente, una columna o relación desconocida o un error de base de datos fallan solo esa entrada; el resto del batch responde normal (cada entrada corre en su SAVEPOINT).

**Personalizar un catálogo** se hace en `_CUSTOM` de `catalogs/registry.py`, sin tocar el endpoint:
- `relations`: la base de datos no declara FKs, así que las relaciones se listan a mano: `"cities": dict(relations={"country": Relation("countries", "country_id")})`. Se cargan con un `WHERE id IN (...)` por relación, como `selectinload`.
- `default_sort`: cambia el orden por defecto.
- `where`: condición fija; por ejemplo `metrics` oculta las filas con `deleted_at`.

Si `registry.py` referencia un catálogo o columna que no existe, la app falla al arrancar, no en la primera request.

**Agregar un catálogo** = agregar su tabla en `catalogs/tables.py` con el tipo real de cada columna (`information_schema`), y correr `pytest -m drift`.

### Cross-feature
- La única frontera entre features es un `services.py` en la feature dueña. Una feature nunca importa el repositorio ni los modelos de otra.
- Excepción: las `Table` de `catalogs/tables.py` son compartidas. Si una feature necesita un catálogo como entidad ORM (p. ej. para eager-load), lo mapea sobre la misma tabla en vez de redefinirla: `class GeneralCity(Base): __table__ = general_cities` (ver `employee/models.py`).

## 6. Estandarización transversal (`shared/`)

Todo lo transversal se escribe una vez en `shared/`. Las features lo consumen vía import o `Depends` y nunca lo copian.

### 6.1 Errores

Jerarquía `AppError` → `NotFoundError` (404), `ConflictError` (409), `InvalidFieldError` (400), cada una con un `code` legible por máquina separado del `detail` legible por humano. El handler global de `main.py` responde:

```json
{"code": "NOT_FOUND", "detail": "employee_positions id -1 not found"}
```

Los errores de validación de Pydantic se normalizan en el mismo lugar:

```json
{"code": "VALIDATION_ERROR", "detail": "Validation error", "errors": [{"field": "...", "message": "...", "type": "..."}]}
```

El frontend ramifica sobre `code`, nunca haciendo string-matching sobre `detail`. Cualquier integración externa futura (ERP, Slack, etc.) debe traducir sus errores en su propio handler, sin dejar escapar la excepción cruda.

### 6.2 Forma de respuesta

```python
class Page(BaseModel, Generic[T]):      # listados
    data: List[T]
    total: int
    page: int
    per_page: int

class Envelope(BaseModel, Generic[T]):  # una entidad
    data: T
```

Se usan siempre como `response_model`. Así el contrato queda documentado automáticamente en Swagger (`/docs`), y un cambio global (por ejemplo, agregar `has_next`) se hace en un solo lugar. Los `XOut` usan `ConfigDict(from_attributes=True)` y se serializan directamente desde los objetos ORM, sin armar dicts a mano.

### 6.3 Validación y permisos: `Depends`, no decoradores propios

Un decorador de Python oculta la firma real de la función, y FastAPI necesita esa firma para construir OpenAPI y para la inyección de dependencias. Por eso la validación y los permisos transversales se hacen con `Depends()`. Si se quiere azúcar con forma de decorador (`@requires_permission("x")`), debe ser una envoltura delgada que agregue un `Depends(check_permission("x"))`; la lógica nunca debe vivir en el decorador. `shared/permissions.py` muestra esa forma, pero hoy es un stub (ver sección 9).

### 6.4 Paginación, orden y filtros

`Pagination` y `Sort` se exponen como **fábricas** de dependencias. La regla de validación vive en un solo lugar, y cada ruta puede pedir otros límites de forma explícita:

```python
pagination: Pagination = Depends(pagination_params())                         # defaults: 20, máx 200
pagination: Pagination = Depends(pagination_params(default_per_page=1000, max_per_page=100_000))  # export
sort: Sort = Depends(sort_params(default_field="id"))
```

Cada feature solo declara su propio `FilterX(BaseModel)`. `merge_query_filters(request, filters)` agrega al dict de filtros cualquier querystring extra que no esté declarada, así que un filtro ad hoc nuevo no obliga a tocar la firma del controller. Las columnas por las que se puede ordenar pasan por una lista blanca en el repositorio (`_SORTABLE_FIELDS`).

Lo que no debe variar por endpoint (la forma del error, `Page[T]`) queda fijo a propósito. La personalización es para los casos que realmente la necesitan.

## 7. Tests

**Probar lo que ve el cliente, contra Postgres real.** Los tests llaman a la app por HTTP y verifican en la base de datos. No hay mocks ni Fakes: prueban que el mock funciona, no el sistema, y se desincronizan del código real.

| Tipo | Dónde | Qué cubre |
|---|---|---|
| **Tests de API** (la mayoría) | `tests/features/<feature>/test_*.py` | Contrato HTTP: rutas, validación, serialización, upsert, savepoints, 404 |
| **Drift de schema** | `tests/test_schema_drift.py` | Que cada modelo coincida con la BD real (tipos, columnas, tablas) |
| Unit tests | `tests/shared/` | Solo funciones con lógica pura (ej. `merge_query_filters`) |

No se escriben tests unitarios de use cases que solo pasan la llamada al repositorio, ni de los repositorios por separado: los tests de API ya los ejecutan de verdad.

```bash
pip install -r requirements-dev.txt
pytest            # requiere Docker corriendo
pytest -m drift   # lee la BD del .env, solo lectura
```

### Cómo funciona (`tests/conftest.py`)

- **testcontainers** levanta un `postgres:15-alpine` (la misma versión mayor que producción) una vez por corrida, y crea las tablas desde los modelos. Un dev nuevo solo necesita Docker.
- **Cada test corre dentro de una transacción que se revierte al final.** La sesión usa `join_transaction_mode="create_savepoint"`, así que el `commit()` de `get_db` y los `begin_nested()` del bulk se convierten en SAVEPOINTs dentro de esa transacción. El código se comporta igual que en producción y no queda nada que limpiar.
- **Fixtures**: `client` (TestClient de la app real) y `db` (la misma sesión que usa el endpoint).
- Para verificar lo que de verdad quedó guardado: `db.expunge_all()` y volver a cargar la fila. Sin eso, `db.get` puede devolver el objeto en memoria de la sesión.

### Por qué existe el test de drift

El contenedor crea las tablas **desde los modelos**, así que nunca va a detectar un modelo que no coincide con la BD real. Ese fue el bug de `monthly_sales_price` (`Integer` vs `numeric(10,2)`). `pytest -m drift` compara cada columna con la BD del `.env` y lista las diferencias. En su primera ejecución encontró `employee_positions.deleted_at` mapeado como `DateTime` cuando es `DATE`. Se corre siempre que se toque un modelo.

### Datos de prueba: factories

`tests/features/<feature>/factories.py` tiene funciones pequeñas que insertan una fila válida con defaults: `make_person(db, first_name="Ana")`. Cada test pasa solo lo que le importa, así se lee como el escenario que verifica. No se usan librerías como `factory_boy`.

### Una feature nueva

Agrega `tests/features/<feature>/` con su `factories.py` y sus `test_*.py`, e importa sus modelos en `conftest.py` (una línea, para que sus tablas se creen). Nada más del `conftest` cambia. Mínimo a cubrir por feature: el listado (filtros, orden, paginación), el detalle (forma anidada y 404), el upsert (crear + actualizar en la misma llamada, fallo parcial, `required_on_create` por recurso) y los deletes.

## 8. Cómo agregar una feature nueva

1. **Verificar los tipos reales** de las tablas en `information_schema.columns`, sobre todo las columnas `numeric`.
2. `features/<feature>/models.py`: los modelos del agregado, con `relationship(..., lazy="raise")` dentro del agregado y enteros planos para los ids de catálogos externos.
3. `features/<feature>/schemas/request.py` y `schemas/response.py`: un `XUpsertItem` por entidad (`id` y todos los campos opcionales) y los `XOut` (`from_attributes=True`).
4. `features/<feature>/repository.py`: `class XRepository(BaseRepository)`, solo con las consultas propias (listado con filtros y `_SORTABLE_FIELDS`, detalle con `selectinload`). Las vistas de solo lectura con SQL propio van en `custom_repository.py` + `sql/<nombre>.sql` (ver "SQL propio" en la sección 5).
5. `features/<feature>/use_cases/query.py` y `write.py`: funciones que reciben `repo`. Para escrituras, se reutiliza el patrón de `employee` (`bulk_upsert` + deletes).
6. `features/<feature>/controller.py`: `router = APIRouter(prefix="/<feature>")`, `get_repository`, un `POST /<recurso>/bulk-upsert` por entidad con su `required_on_create`, deletes aparte, rutas estáticas antes que las de parámetro, `response_model` en todo.
7. Registrarlo en `app/api/v1.py` con `router.include_router(...)`.
8. Tests en `tests/features/<feature>/` (ver sección 7) y `pytest -m drift` para validar los modelos.
9. Si la feature crea tablas: su migración con el `GRANT` al rol de la app, en el mismo PR (ver sección 9).

## 9. Pendientes y decisiones abiertas

- **Autenticación**: no existe. `shared/permissions.py` es un stub que lee un header. Antes de exponer el BFF, hay que agregar una feature de auth y poner `dependencies=[Depends(get_current_user)]` en cada router.
- **Migraciones**: aún no hay Alembic. Regla para cuando se cree cualquier tabla: la migración y el `GRANT` al rol de la app van en el mismo PR. Una tabla que existe en la base sin permisos coordinados es una caída de producción en espera.
- **Ruta del detalle**: hoy es `GET /employee/details/{id}`; el alias `GET /employee/persons/{id}` está comentado en el controller. Falta decidir si se elimina del todo o se vuelve a la forma REST `/persons/{id}`.
- **Creación de personas y assignations**: el bulk-upsert habilita crear `employee_persons` (requiere `first_name`, `last_name`) y `operation_assignations` (requiere `operational_profile_id`), algo que la ventana de Retool no hacía. Si no se quiere permitir, se agrega una validación que rechace ítems sin `id` en esos dos endpoints.
- **`shared/projection.py`** (`parse_fields`): portado de `bff-lsg-placement` pero sin usar. Una proyección dinámica de campos choca con un `response_model` fijo; falta decidir si se adopta.
- **Tablas no modeladas**: `employee_comments`, `employee_person_comments`, `company_tech_partners` y `cost_employee_history` están en la especificación (Anexo A) sin operaciones definidas. Se agregan cuando haya un requerimiento concreto.
- **Catálogos**:
  - `general_action_plan_statuses` (Anexo B) no existe en la base de datos; ¿es `general_action_statuses`? Hasta confirmarlo no se expone ninguna de las dos.
  - `general_silo` del Anexo B es `general_silos` en la base de datos; se expone como `silos`.
  - El catálogo `technologies` es la tabla `technologies` (a la que apunta `employee_technologies.technology_id`), no `general_technologies`, que está vacía y no se expone. 717 filas de `employee_technologies` apuntan a ids que no existen en `technologies`.
  - Existen en la base pero no están en el Anexo B, así que no se exponen: `general_action_statuses`, `general_companies`, `general_cycles`, `general_financial_dimensions`, `general_resource_release_autonomy`, `general_status`.
  - Solo lectura por ahora. Las escrituras serían un `POST /catalogs/{catalog}/bulk-upsert` sobre el mismo registro.
  - No se puede filtrar por columnas de una relación (`"country.name": "..."`), como sí permitía placement; se agrega si aparece el caso.
- **Riesgos del ORM**: el N+1 está mitigado por diseño con `lazy="raise"`. Lo que sí exige aprendizaje es entender el *unit of work* y el identity map de la sesión (por qué `flush` no es `commit`, por qué un objeto modificado se persiste sin llamar a `save`).

---

## Anexo A — Especificación original del módulo Employee (Retool)

El módulo `employee` reemplaza la ventana de edición de un solo empleado en Retool. Lo que sigue es el material de origen, tal como venía de Retool, y se conserva como referencia de qué se migró.

> ⚠️ **Los tipos de columna de este anexo no son confiables.** Retool reportaba como `integer` columnas que en Postgres son `numeric(10,2)`: `salary`, `additional_salary`, `cost`, `allocation`, `monthly_sales_price` y `hourly_sales_price`, además de `bonus`, que es `numeric(4,3)`. La fuente de verdad es `information_schema.columns` (ver sección 5, "Modelos y tipos").

### Tablas

```json
[
  {
    "entity_name": "employee_comments",
    "columns": {
      "id": "integer",
      "person_id": "integer",
      "comment": "string",
      "retool_user": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "employee_person_comments",
    "columns": {
      "id": "integer",
      "person_id": "integer",
      "comment": "string",
      "reported_by": "string",
      "is_active": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "company_tech_partners",
    "columns": {
      "id": "integer",
      "person_id": "integer",
      "is_active": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "employee_persons",
    "columns": {
      "id": "integer",
      "first_name": "string",
      "last_name": "string",
      "identification_type_id": "integer",
      "city_id": "integer",
      "identification": "string",
      "photo_url": "string",
      "nationality_id": "integer",
      "birth_date": "timestamp",
      "phone_number": "string",
      "personal_email": "string",
      "corporate_email": "string",
      "address": "string",
      "cv_url": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "cost_employee_history",
    "columns": {
      "id": "integer",
      "assignation_id": "integer",
      "assignation_silo_id": "integer",
      "assignation_cost_center_id": "integer",
      "person_id": "integer",
      "account_id": "integer",
      "cycle_id": "integer",
      "position_id": "integer",
      "position_silo_id": "integer",
      "position_cost_center_id": "integer",
      "real_cost": "integer",
      "salary": "integer",
      "cost": "integer",
      "prorated_cost": "integer",
      "prorate_days": "integer",
      "is_billable": "boolean",
      "employee_role_id": "integer",
      "notes": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "po_number": "string"
    }
  },
  {
    "entity_name": "employee_positions",
    "columns": {
      "id": "integer",
      "employee_role_id": "integer",
      "contract_type_id": "integer",
      "currency": "string",
      "start_date": "timestamp",
      "end_date": "timestamp",
      "salary": "integer",
      "additional_salary": "integer",
      "cost": "integer",
      "bonus": "integer",
      "is_active": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "silo_id": "integer",
      "cost_center_id": "integer",
      "effective_date": "timestamp",
      "deleted_at": "timestamp"
    }
  },
  {
    "entity_name": "employee_roles",
    "columns": {
      "id": "integer",
      "person_id": "integer",
      "role_id": "integer",
      "seniority_id": "integer",
      "is_main": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "general_seniorities",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "order": "integer"
    }
  },
  {
    "entity_name": "operation_assignations",
    "columns": {
      "id": "integer",
      "account_id": "integer",
      "operational_profile_id": "integer",
      "allocation": "integer",
      "effective_date": "timestamp",
      "end_date": "timestamp",
      "notes": "string",
      "is_billable": "boolean",
      "monthly_sales_price": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "silo_id": "integer",
      "cost_center_id": "integer",
      "start_date": "timestamp",
      "reason_id": "integer",
      "end_reason_id": "integer",
      "is_onboarding": "boolean",
      "is_offboarding": "boolean",
      "placement_id": "string",
      "financial_dimension_id": "integer",
      "payment_in_arrears": "boolean",
      "po_number": "string",
      "hourly_sales_price": "integer",
      "monthly_agreed_hours": "integer"
    }
  },
  {
    "entity_name": "employee_operational_profiles",
    "columns": {
      "id": "integer",
      "employee_role_id": "integer",
      "is_certified": "boolean",
      "is_available": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "employee_technologies",
    "columns": {
      "id": "integer",
      "person_id": "integer",
      "seniority_id": "integer",
      "technology_id": "integer",
      "is_principal": "boolean",
      "is_verified": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "knowledge_external_id": "integer",
      "seniority_external_id": "integer"
    }
  },
  {
    "entity_name": "technologies",
    "columns": {
      "id": "integer",
      "name": "string",
      "provider": "string",
      "role_id": "integer",
      "language_id": "integer",
      "category_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "tech_id": "integer"
    }
  },
  {
    "entity_name": "general_languages",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "employee_languages",
    "columns": {
      "id": "integer",
      "person_id": "integer",
      "language_id": "integer",
      "language_level_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "general_language_levels",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "general_hardwares",
    "columns": {
      "id": "integer",
      "name": "string",
      "hardware_ref": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "employee_equipments",
    "columns": {
      "id": "integer",
      "person_id": "integer",
      "hardware_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  }
]
```

### Lecturas (las 7 queries que reemplaza `GET /employee/details/{id}`)

```sql
select
  ep.first_name
  , ep.last_name
  , ep.identification_type_id
  , ep.city_id
  , ep.identification
  , ep.photo_url
  , ep.nationality_id
  , ep.birth_date
  , ep.phone_number
  , ep.personal_email
  , ep.corporate_email
  , ep.address
  , ep.cv_url
  , gc.country_id
from employee_persons ep
left join general_cities gc on
  ep.city_id = gc.id
where ep.id = {{ person_id.value }}
```

```sql
select
  er.id employee_role_id
  , er.role_id
  , er.seniority_id
  , er.is_main
  , eop.id employee_operational_profile_id
  , eop.is_certified
  , eop.is_available
  , max(ep.id)::bool has_active_employee_position
  , max(oa.id)::bool has_active_employee_assignation
from employee_roles er
inner join employee_operational_profiles eop on
  eop.employee_role_id = er.id
left join employee_positions ep on
  ep.employee_role_id = er.id and ep.is_active
left join operation_assignations oa on
  oa.operational_profile_id = eop.id and (oa.end_date isnull or oa.end_date > current_date)
where person_id = {{ person_id.value }}
group by er.id, eop.id
```

```sql
select
  ep.id employee_position_id
  , er.role_id
  , er.seniority_id
  , ep.is_active
  , ep.start_date
  , ep.effective_date
  , ep.end_date
  , ep.cost_center_id
  , ep.silo_id
  , ep.bonus
  , ep.salary
  , ep.cost
  , ep.currency
  , ep.employee_role_id
  , ep.contract_type_id
  , ep.additional_salary
  , ep.contract_type_id
from employee_positions ep
inner join employee_roles er on
ep.employee_role_id = er.id
where
  er.person_id = {{ person_id.value }}
order by
  ep.start_date desc, ep.effective_date desc, ep.end_date desc
```

```sql
select
  oa.id assignation_id
  , er.role_id
  , er.seniority_id
  , oa.account_id
  , oa.is_billable
  , oa.is_onboarding
  , oa.is_offboarding
  , oa.payment_in_arrears
  , oa.monthly_sales_price
  , oa.start_date
  , oa.effective_date
  , oa.end_date
  , oa.cost_center_id
  , oa.allocation
  , oa.reason_id
  , oa.end_reason_id
  , oa.notes
  , oa.operational_profile_id
  , oa.placement_id
  , oa.financial_dimension_id
  , oa.po_number
  , oa.hourly_sales_price
  , oa.monthly_agreed_hours
from operation_assignations oa
inner join employee_operational_profiles eop on
  oa.operational_profile_id = eop.id
inner join employee_roles er on
  eop.employee_role_id = er.id
where
  er.person_id = {{ person_id.value }}
order by
  oa.start_date desc, oa.effective_date desc
```

```sql
select
  et.id
  , et.technology_id
  , et.seniority_id
  , et.is_principal
  , et.is_verified
from employee_technologies et
where
  et.person_id = {{ person_id.value }}
```

```sql
select
  el.id
  , el.language_id
  , el.language_level_id
from employee_languages el
where
  el.person_id = {{ person_id.value }}
```

```sql
select
  ee.id
  , ee.hardware_id
from employee_equipments ee
where
  ee.person_id = {{ person_id.value }}
```

### Escrituras y su endpoint equivalente

Todas las escrituras de creación/actualización de Retool quedaron cubiertas por un `bulk-upsert` por entidad. Una sola fila se envía como lista de un ítem.

| Operaciones en Retool | Endpoint |
|---|---|
| employee_persons: update by id | `POST /employee/persons/bulk-upsert` |
| employee_roles: insert one | `POST /employee/roles/bulk-upsert` |
| employee_operational_profiles: insert one, bulk update | `POST /employee/operational-profiles/bulk-upsert` |
| employee_positions: insert one, update one by id, bulk update | `POST /employee/positions/bulk-upsert` |
| operation_assignations: bulk update | `POST /employee/assignations/bulk-upsert` |
| employee_technologies: insert one, bulk update, bulk upsert | `POST /employee/technologies/bulk-upsert` |
| employee_languages: insert one, bulk update via primary key | `POST /employee/languages/bulk-upsert` |
| employee_equipments: insert one, bulk update | `POST /employee/equipments/bulk-upsert` |
| `delete from employee_technologies where id = ANY(...)` | `DELETE /employee/technologies?ids=...` |
| `delete from employee_languages where id = ...` | `DELETE /employee/languages/{id}` |
| `delete from employee_equipments where id = ...` | `DELETE /employee/equipments/{id}` |

## Anexo B — Catálogos (`general_*`)

Lista de origen de los catálogos que expone `POST /catalogs`. Igual que en el Anexo A, **los tipos no son confiables**: `catalogs/tables.py` se generó desde `information_schema` (p. ej. `estimated_time` es `double precision`, no `integer`; `general_overtime_types.days` es un arreglo de texto).

```json
{
    "entity_name": "general_seniorities",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "order": "integer"
    }
  },
  {
    "entity_name": "general_languages",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
    {
    "entity_name": "general_language_levels",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "general_hardwares",
    "columns": {
      "id": "integer",
      "name": "string",
      "hardware_ref": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },

  {
    "entity_name": "general_absent_status",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "general_absent_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
  {
    "entity_name": "general_account_activities",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
    {
    "entity_name": "general_account_activity_processes",
    "columns": {
      "id": "integer",
      "name": "string",
      "estimated_time": "integer",
      "is_active": "boolean",
      "code": "string",
      "rule_code": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  },
   {
    "entity_name": "general_account_categories",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "type": "string",
    }
  },
    {
    "entity_name": "general_account_phases",
    "columns": {
      "id": "integer",
      "name": "string",
      "account_type_id": "integer",
      "account_status_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
    {
    "entity_name": "general_account_statuses",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
      {
    "entity_name": "general_account_training_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
        {
    "entity_name": "general_account_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
          {
    "entity_name": "general_action_plan_responsibles",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_action_plan_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_action_plan_statuses",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_actions",
    "columns": {
      "id": "integer",
      "name": "string",
      "type": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_attachment_subtype",
    "columns": {
      "id": "integer",
      "name": "string",
      "type_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
    {
    "entity_name": "general_attachment_type",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_augmented_services",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_bill_account_statuses",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_business_review_topics",
    "columns": {
      "id": "integer",
      "name": "string",
      "is_system": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_ceremonies",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_cities",
    "columns": {
      "id": "integer",
      "name": "string",
      "country_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_client_coverage_status",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_color_disc",
    "columns": {
      "id": "integer",
      "name": "string",
    }
  },
  {
    "entity_name": "general_competences",
    "columns": {
      "id": "integer",
      "name": "string",
      "type": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_contract_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "is_active": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_cost_centers",
    "columns": {
      "id": "integer",
      "profit_loss_id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_countries",
    "columns": {
      "id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_document_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_equipments",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_exception_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_exceptions",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "additional_charges": "string",
      "subtract_charges": "string",
      "exception_type_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_financial_dimension_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "level": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_flags",
    "columns": {
      "id": "integer",
      "name": "string",
      "order": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_frequencies",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_governance_categories",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_governance_concept_type_values",
    "columns": {
      "id": "integer",
      "name": "string",
      "concept_type_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_governance_concept_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "is_value": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_governance_concepts",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "affect_billing": "boolean",
      "customer_visibility": "boolean",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "category_id": "integer",
      "concept_type_id": "integer",
      "default_value": "string",
    }
  },
  {
    "entity_name": "general_hardwares",
    "columns": {
      "id": "integer",
      "name": "string",
      "hardware_ref": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_holidays",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "holiday_date": "timestamp",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "country_code": "string",
      "last_updated_by": "string",
    }
  },
  {
    "entity_name": "general_improvement_request_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_industries",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_issue_categories",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_issue_statuses",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_language_levels",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_languages",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_learning_platforms",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_manager_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_metrics",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "deleted_at": "timestamp",
    }
  },
  {
    "entity_name": "general_newsletters",
    "columns": {
      "id": "integer",
      "content": "string",
      "url_link": "string",
      "category": "string",
      "retool_user": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_offer_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_origins",
    "columns": {
      "id": "integer",
      "name": "string",
      "type": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_outcome_reporters",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_overtime_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "days": "string",// TODO
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_payment_platform",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_payroll_novelties",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "payroll_novelty_type_id": "integer",
      "is_deprecated": "boolean",
    }
  },
  {
    "entity_name": "general_payroll_novelty_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_placement_status",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_pmb_concept",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_poc_positions",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_priorities",
    "columns": {
      "id": "integer",
      "name": "string",
      "type": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_profit_and_loss",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_reasons",
    "columns": {
      "id": "integer",
      "name": "string",
      "type": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_recurrences",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_related_exception_and_payroll_novelty",
    "columns": {
      "id": "integer",
      "exception_id": "integer",
      "payroll_novelty_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_replacing_options",
    "columns": {
      "id": "integer",
      "name": "string",
      "type": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_resource_release_improvement",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_resource_release_strength",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_retention_responsibles",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_retention_statuses",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_review_sources",
    "columns": {
      "id": "integer",
      "name": "string",
      "type": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_risk_statuses",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "color": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_roles",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_salary_request_change_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_salary_request_decision_makers",
    "columns": {
      "id": "integer",
      "name": "string",
      "is_active": "boolean",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_salary_request_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_seniorities",
    "columns": {
      "id": "integer",
      "name": "string",
      "order": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_silo_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_silo",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "report_to_silo_id": "integer",
      "silo_type_id": "integer",
      "manager_id": "integer",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_sub_account_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_technologies",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_technology_categories",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_technology_languages",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_tps",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_training_analysis_classification",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_training_attempt_link",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_training_decisions",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_training_open_positions",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_training_source",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_training_status",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_training_workflows",
    "columns": {
      "id": "integer",
      "name": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_warrior_types",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  {
    "entity_name": "general_work_modalities",
    "columns": {
      "id": "integer",
      "name": "string",
      "description": "string",
      "created_at": "timestamp",
      "updated_at": "timestamp",
    }
  },
  ```

  ```sql
 SELECT DISTINCT ON (ca.name) ca.name "account", grs.name "status", grs.color
FROM pcu_responses pcu
LEFT JOIN general_risk_statuses grs ON pcu.risk_status_id = grs.id
LEFT JOIN operation_assignations oa ON pcu.assignation_id = oa.id
LEFT JOIN company_accounts ca ON oa.account_id = ca.id
LEFT JOIN employee_operational_profiles eop ON oa.operational_profile_id = eop.id
LEFT JOIN employee_roles er ON eop.employee_role_id = er.id
WHERE er.person_id = {{ +person_id.value }}
ORDER BY ca.name, pcu.created_at DESC
```

```sql

```

```sql
select id, name, "order" from general_seniorities
```


```sql
with tech AS (
	SELECT ep.id, string_agg(t.name, ', ') as tech_stack
  	FROM employee_persons AS ep  
  	LEFT JOIN employee_technologies AS et on ep.id = et.person_id
  	LEFT JOIN technologies AS t ON et.technology_id = t.id 
  	GROUP BY ep.id
),
main_tech AS (
	SELECT ep.id, t.name AS main_tech
	FROM employee_persons AS ep  
	LEFT JOIN employee_technologies AS et on ep.id = et.person_id
	LEFT JOIN technologies AS t ON et.technology_id = t.id 
	WHERE et.is_principal
),
langs AS (SELECT ep.id, string_agg(gl.name, ', ') as language_stack
   FROM employee_persons AS ep  
   LEFT JOIN employee_languages AS el on ep.id = el.person_id 
   LEFT JOIN general_languages AS gl on el.language_id = gl.id
   GROUP BY ep.id
),
employee AS (
	select er.id as role_id
		,concat_ws(' ', ep.first_name, ep.last_name) as fullname
        ,ep.first_name
        ,ep.last_name
		,ep.id as employee_id
	    ,ep.personal_email
		,ep.corporate_email as email
		,ep.phone_number
	    ,ep.photo_url
	    ,ep.address
	    ,ep.identification
	    ,ep.birth_date 
	    ,gc.name as city
	    ,gco.name as country
	    ,gna.name as nacionality
	    ,gdt.name as identification_type 
		,gs.name as seniority
		,gr.name as role
		,tech.tech_stack
		,main_tech.main_tech
		,langs.language_stack
	from employee_persons ep 
	inner join employee_roles er on ep.id = er.person_id
	inner join general_roles gr on er.role_id = gr.id
	inner join general_seniorities gs on er.seniority_id = gs.id
	left join general_cities gc ON ep.city_id = gc.id
	left join general_countries gco on gc.country_id = gco.id
	left join general_countries gna on ep.nationality_id = gna.id
	left join general_document_types gdt on ep.identification_type_id = gdt.id
	left join tech on ep.id = tech.id
    left join main_tech on ep.id = main_tech.id
    left join langs on ep.id = langs.id
	where ep.id = {{ EMPLOYEE.value.person_id }}
)
select *
from employee;
```


```sql
with
positions as (
	select ep.id as employee_id
		,epos.id as position_id
		,epos.cost
        ,epos.salary
		,er.id as role_id
		,epos.start_date
		,epos.effective_date
		,epos.end_date
		,epos.contract_type_id
		,(case when epos.end_date is null then true else false end) as is_active
	from employee_persons ep 
	inner join employee_roles er on ep.id = er.person_id
	inner join employee_positions epos on er.id = epos.employee_role_id
    where epos.deleted_at is null and
          ep.id = {{ EMPLOYEE.value.person_id }}
),
  assignations as (
	select oa.id as assignation_id
		,ca.name as account
        ,ca.account_type_id
		,ca.manager_id
		,gat.name as account_type
		,ca.billing_cycle
		,oa.account_id
		,oa.monthly_sales_price * oa.allocation as sales_price
		,er.id as role_id
		,ep.id as employee_id
		,gs.name as seniority
		,gr.name as role
		,oa.is_billable
        ,oa.cost_center_id
		,oa.allocation
		,oa.start_date
		,oa.effective_date
		,oa.end_date
		,oa.monthly_sales_price
        ,oa.po_number
		,gcc.name as cost_center
		,gpal.name as p_l_category
		,gsi.name silo_name
        ,ca.manager_id
        ,concat_ws(' ', ep_manager.first_name, ep_manager.last_name) "manager"
        , gfd.name financial_dimension
	from employee_persons ep 
	inner join employee_roles er on ep.id = er.person_id
	inner join general_roles gr on er.role_id = gr.id
	inner join general_seniorities gs on er.seniority_id = gs.id 
	inner join employee_operational_profiles eop on er.id = eop.employee_role_id 
	inner join operation_assignations oa on oa.operational_profile_id = eop.id
	inner join company_accounts ca on oa.account_id = ca.id
	inner join general_account_types gat on ca.account_type_id = gat.id
	inner join general_cost_centers gcc on oa.cost_center_id = gcc.id
	inner join general_profit_and_loss gpal on gcc.profit_loss_id = gpal.id
    left join general_silos gsi on oa.silo_id = gsi.id
    left join employee_operational_profiles eop_manager ON ca.manager_id = eop_manager.id
    left join employee_roles er_manager ON eop_manager.employee_role_id = er_manager.id
    left join employee_persons ep_manager ON er_manager.person_id = ep_manager.id
    left join general_financial_dimensions gfd on oa.financial_dimension_id = gfd.id
    where ep.id = {{ EMPLOYEE.value.person_id }}
),
posi_assig as (
	select a.*
		,p.position_id
        ,p.salary
		,p.cost as employee_cost
		,p.is_active
		,p.end_date as position_end_date
	from assignations a 
	inner join positions p on p.employee_id = a.employee_id
    where (
    		p.effective_date <= a.effective_date and 
    		a.effective_date <= p.end_date and
    		(a.end_date is null OR p.end_date <= a.end_date)
    )
    	OR (
    		a.effective_date <= p.effective_date and
    		p.effective_date <= a.end_date and 
    		(p.end_date is null OR p.end_date <= a.end_date)
    )   OR (
    		a.effective_date <= p.effective_date and
    		p.effective_date <= a.end_date and 
    		(p.end_date is null OR p.end_date >= a.end_date)
    )	OR (
    		p.effective_date <= a.effective_date and 
    		(p.end_date is null or p.end_date >= a.end_date)
    )	OR (
    	a.effective_date <= p.effective_date and
    	(a.end_date is null OR p.end_date <= a.end_date)
    )
)
select *,
  (case when (is_billable and sales_price > 0)
	then (sales_price - employee_cost) / sales_price else 0 end) as margin
from posi_assig
order by posi_assig.is_active desc, start_date desc, effective_date desc
```


```sql
select rew.id, gwt."name" as ew_status, rew.created_at as last_evaluation_date
from employee_persons ep
inner join employee_roles er on ep.id = er.person_id
inner join employee_positions epos on er.id = epos.employee_role_id
inner join report_employee_warrior rew on epos.id = rew.employee_position_id
inner join general_warrior_types gwt on gwt.id = rew.warrior_type_id
where ep.id = {{ EMPLOYEE.value.person_id }}
```


```sql
select ep.id as person_id
    , gl."name" as language
    , gll."name" as level
    , el.created_at as last_evaluation_date
from employee_persons ep
inner join employee_languages el on el.person_id = ep.id
inner join general_languages gl on gl.id = el.language_id 
inner join general_language_levels gll on el.language_level_id = gll.id 
where el.language_level_id = 3 -- english
  and ep.id = {{ EMPLOYEE.value.person_id }}
```

```sql
with exp_employee_accounts as (
	select MAX(exp_emp.lt_exp_tech_in_days) as exp_in_days
		, exp_emp.person_id
		, exp_emp.account_id
		, MAX(exp_emp.account) as account
		, exp_emp.technology_id
		, MAX(exp_emp.technology) as technology
	from (
		select ep.id as person_id
			, (oa.account_id) as account_id
			, (ca."name") as account
			, abs(extract(
				day from (oa.start_date)::timestamp 
				- 
				(case when (oa.end_date) is null
				then CURRENT_DATE::timestamp
				else (oa.end_date)::timestamp end)
			)) as lt_exp_tech_in_days
			, (oa.start_date) as start_date
			, (oa.end_date) as end_date 
			, (ta.technology_id) as technology_id
			, (t."name") as technology
		from employee_persons ep 
		inner join employee_roles er on ep.id = er.person_id
		inner join employee_operational_profiles eop on er.id = eop.employee_role_id
		inner join operation_assignations oa ON eop.id = oa.operational_profile_id
		inner join company_accounts ca on oa.account_id = ca.id
		inner join technology_accounts ta on oa.account_id = ta.account_id
		inner join technologies t on t.id = ta.technology_id
		where ep.id = {{ EMPLOYEE.value.person_id }}
	) as exp_emp
	group by exp_emp.account_id, exp_emp.person_id, exp_emp.technology_id
),
employee_tech as (
	select ep.id
		, t.id as technology_id
		, t."name" as technology
		, gtc."name" as type
		, gs."name" as seniority
		, exp_ea.exp_in_days
		, TRUNC((coalesce(exp_in_days, 0) / 365),1) as "exp_in_year"
		, exp_ea.account_id
		, exp_ea.account
	from employee_persons ep 
	inner join employee_roles er on ep.id = er.person_id
	inner join employee_technologies et on ep.id = et.person_id
	inner join general_seniorities gs on et.seniority_id = gs.id
	inner join technologies t on et.technology_id = t.id
	inner join general_technology_categories gtc on gtc.id = t.category_id
	left join exp_employee_accounts exp_ea on exp_ea.person_id = ep.id
		and exp_ea.technology_id = t.id
	where ep.id = {{ EMPLOYEE.value.person_id }}
)
select *
from employee_tech
```

```sql
select
  array_agg(distinct oa.account_id) account_ids
from operation_assignations oa 
inner join employee_operational_profiles eop on 
  oa.operational_profile_id = eop.id
  and (oa.end_date isnull or oa.end_date >= current_date)
inner join employee_roles er on 
  eop.employee_role_id = er.id
  and er.person_id = {{ person_id.value  }}

```

```sql
SELECT er.role_id
 , gs.name as seniority
 , gr.name AS role
 , er.is_main
 , eop.is_certified
 , eop.is_available
from employee_persons as e
inner join employee_roles as er on er.person_id = e.id
inner join employee_operational_profiles as eop on eop.employee_role_id = er.id
inner join general_seniorities gs on er.seniority_id = gs.id 
inner join general_roles as gr on er.role_id = gr.id
where e.id = {{ EMPLOYEE.value.person_id }}
```

```sql
SELECT ep.id
     , ep.contract_type_id
     , ep.currency
     , ep.start_date
     , ep.effective_date
     , ep.end_date
     , ep.salary
     , ep.additional_salary
     , ep.is_active
     , ep.cost     
     , ep.bonus
     , ep.silo_id
     , ep.cost_center_id
     , gr.name employee_role
     , ct.name contract_type
     , cc.name cost_center
     , gs.name seniority
     , si.name silo
FROM employee_positions AS ep
LEFT JOIN employee_roles AS er ON ep.employee_role_id = er.id
LEFT JOIN general_roles AS gr ON er.role_id = gr.id
LEFT JOIN general_contract_types AS ct ON ep.contract_type_id = ct.id
LEFT JOIN general_cost_centers AS cc ON ep.cost_center_id = cc.id
LEFT JOIN general_seniorities AS gs ON er.seniority_id = gs.id
LEFT JOIN general_silos AS si ON ep.silo_id = si.id
WHERE er.person_id = {{ EMPLOYEE.value.person_id }}
order by ep.is_active DESC, ep.id DESC 
```

```sql
select MAX(gs."name") as seniority,
	MAX(gs.order) as score,
	gr.name as "role_name"
from employee_technologies et
inner join general_seniorities gs on et.seniority_id = gs.id
inner join technologies t on et.technology_id = t.id
inner join general_roles gr on t.role_id = gr.id
where et.person_id = {{ EMPLOYEE.value.person_id }}
group by gr.name
```

```sql
select gs."name" as seniority,
	gs.order as score,
	t."name" as tech,
	gr.name as "role_name"
from employee_technologies et
inner join general_seniorities gs on et.seniority_id = gs.id
inner join technologies t on et.technology_id = t.id
inner join general_roles gr on t.role_id = gr.id
where et.person_id = {{ EMPLOYEE.value.person_id }}
and ({{graph_seniority_roles.selectedPoints.length == 0}} or
  gr.name ILIKE {{'%' + graph_seniority_roles.selectedPoints[0]?.x + '%'}})
```

- actions


```sql
select gs."name" as seniority,
	gs.order as score,
	et.knowledge_external_id
from employee_technologies et
inner join general_seniorities gs on et.seniority_external_id = gs.id
where et.person_id = {{ EMPLOYEE.value.person_id }}
```

```sql
SELECT id, name, start_date, end_date FROM general_cycles
```

```sql
SELECT id, name FROM general_exceptions
```

```sql
SELECT id, name FROM general_reasons
```

```sql
 SELECT
     be.id
   , concat_ws(' ', ep.first_name, ep.last_name) "name"
   , be.exception_id
   , ge.name "exception"
   , be.cycle_id
   , gc."start_date"::date "cycle"
   , be.account_id
   , ca."name" "account"
   , be.reason_id
   , gr.name "reason"
   , be.start_date
   , be.end_date
   , be.value
   , be.transactional_fee
   , be.approved_by
   , be.is_billed
   , be.notes
   , be.assignation_id
FROM bill_exceptions be
LEFT JOIN operation_assignations oa ON oa.id = be.assignation_id
LEFT JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
LEFT JOIN employee_roles er ON er.id = eop.employee_role_id
LEFT JOIN employee_persons ep ON ep.id = er.person_id
LEFT JOIN general_exceptions ge ON ge.id = be.exception_id
LEFT JOIN general_cycles gc ON gc.id = be.cycle_id
LEFT JOIN company_accounts ca ON ca.id = be.account_id
LEFT JOIN general_reasons gr ON gr.id = be.reason_id
WHERE ep.id = {{ EMPLOYEE.value.person_id }}
```

```sql
 SELECT * FROM general_companies
```

```sql
 SELECT 
  emp_actions.id, 
  emp_actions.action_id,
  g_action.name AS action_name,
  emp_actions.description,
  emp_actions.start_date, 
  emp_actions.end_date,
  emp_actions.action_status_id,
  g_action_status.name AS action_status_name,
  emp_actions.is_completed
FROM employee_actions AS emp_actions
LEFT JOIN general_actions AS g_action ON 
  emp_actions.action_id = g_action.id
LEFT JOIN general_action_statuses AS g_action_status ON
  emp_actions.action_status_id = g_action_status.id
WHERE person_id = {{ EMPLOYEE.value.person_id }} 
```

```sql
 SELECT id, name FROM company_accounts
```

```sql
 SELECT id, comment, retool_user, created_at FROM employee_comments
WHERE person_id = {{ EMPLOYEE.value.person_id }}

```



alejandrooooooooo

```sql
SELECT  
  emp_person.id,
  concat_ws(' ', emp_person.first_name, emp_person.last_name ) As name,
  string_agg (gen_rol.name, ', ') filter (where emp_rol.is_main) AS role,
  --emp_op_prof.id AS employee_operational_profile_id  
  array_agg (emp_op_prof.id) profile_ids
FROM employee_persons emp_person
INNER JOIN employee_roles AS emp_rol ON emp_rol.person_id = emp_person.id 
INNER JOIN general_roles AS gen_rol ON emp_rol.role_id =  gen_rol.id
INNER JOIN employee_operational_profiles AS emp_op_prof ON emp_op_prof.employee_role_id = emp_rol.id
 LEFT JOIN employee_roles er on er.person_id = emp_person.id
LEFT JOIN employee_positions AS em_po ON er.id = em_po.employee_role_id
LEFT JOIN general_silos as gen_silos ON em_po.silo_id = gen_silos.id
WHERE
  gen_rol.name in ('Project Manager', 'Account Manager', 'Account Manager Lead', 'Key Account Manager') and
  case when gen_rol.name = 'Key Account Manager' then true
  	else gen_silos.name NOT IN ('Dedicated')
  end AND
  em_po.is_active 
 group by emp_person.id
  order by  emp_person.first_name 
```

```sql
SELECT gs.id,gs.name
  from  general_silos gs 
where gs.name like {{ 'Dedicated Team'+ '%'}}
```

```sql
 with langs AS (
	SELECT ep.id, string_agg(gl.name, ', ') as language_stack
   FROM employee_persons AS ep  
   LEFT JOIN employee_languages AS el on ep.id = el.person_id 
   LEFT JOIN general_languages AS gl on el.language_id = gl.id
   GROUP BY ep.id
)  
, langs2 AS (
	SELECT ep.id, gll.name as english_level
    FROM employee_persons AS ep  
    LEFT JOIN employee_languages AS el on ep.id = el.person_id 
    LEFT JOIN general_language_levels AS gll on el.language_level_id = gll.id
    WHERE el.language_id = 2  
)
, positions as (
	select
		ep.id as person_id
		, epos.id
        , er.role_id
  		, epos.employee_role_id
		, epos.contract_type_id
		, epos.cost_center_id
		, epos.start_date
		, epos.end_date
		, epos.effective_date
		, (case when epos.end_date is null then true
			when epos.end_date >= current_date then true
			else false end) as pos_is_active
	from employee_persons ep 
	inner join employee_roles er on er.person_id = ep.id
	inner join employee_positions epos on epos.employee_role_id = er.id
)
, pr as (
   select e.id as ep_id
     , gs.name as seniority
     , gr.name as role 
     , e.first_name
     , e.last_name
     , langs.language_stack
     , COALESCE(langs2.english_level, 'Others') as english_level
    from employee_persons as e
    inner join employee_roles as er on er.person_id = e.id
    inner join employee_operational_profiles eop on er.id = eop.employee_role_id 
	inner join operation_assignations oa on oa.operational_profile_id = eop.id
	inner join company_accounts ca on oa.account_id = ca.id
    inner join positions p on er.id = p.employee_role_id
    left join langs ON e.id = langs.id
    left join langs2 ON e.id = langs2.id      
    left join general_roles AS gr on er.role_id = gr.id
    left join general_seniorities as gs on er.seniority_id = gs.id
    where (p.start_date <= oa.effective_date and (p.end_date is null or p.end_date >= oa.end_date))
        and ({{ !employee_ids_filters.value.length }} OR e.id = any({{ employee_ids_filters.value }}) ) 
    	and (({{ show_employees.value }} = 'all') or p.pos_is_active = (case when {{ show_employees.value }} = 'active' then true else false end))
    	and ({{ !filter_by_roles.value.length }} or p.role_id = ANY({{ filter_by_roles.value }}) )
        and ({{ !filter_by_contract_types.value.length }} or p.contract_type_id = ANY({{ filter_by_contract_types.value }}))
        and ({{ !filter_by_cost_center.value.length }} or p.cost_center_id = ANY({{ filter_by_cost_center.value }}))
        and (case
	      when {{ show_type_dates.value }} = 'start_date'
	      	then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
          when {{show_type_dates.value }} = 'end_date'
          	then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
          	else oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}} end)
        and ({{ !filter_by_accounts.value.length }} or oa.account_id = ANY({{ filter_by_accounts.value }}))
		and ({{ !filter_by_account_types.value.length }} or ca.account_type_id = ANY({{ filter_by_account_types.value }}))
        and ({{ !filter_by_managers.value.length }} or ca.manager_id = ANY({{ filter_by_managers.value }}))
)
select pr.english_level, count(pr.ep_id) 
from pr
group by pr.english_level
```

```sql
 with positions as (
	select
		ep.id as person_id
		, epos.id
        , er.role_id
  		, epos.employee_role_id
		, epos.contract_type_id
		, epos.cost_center_id
		, epos.start_date
		, epos.end_date
		, epos.effective_date
		, (case when epos.end_date is null then true
			when epos.end_date >= current_date then true
			else false end) as pos_is_active
	from employee_persons ep 
	inner join employee_roles er on er.person_id = ep.id
	inner join employee_positions epos on epos.employee_role_id = er.id
)
, pr as (
   select e.id as ep_id
     , gs.name as seniority
     , gr.name as role 
     , e.first_name
     , e.last_name
    from employee_persons as e
    inner join employee_roles as er on er.person_id = e.id
    inner join employee_operational_profiles eop on er.id = eop.employee_role_id 
	inner join operation_assignations oa on oa.operational_profile_id = eop.id
	inner join company_accounts ca on oa.account_id = ca.id
    inner join positions p on er.id = p.employee_role_id     
    left join general_roles AS gr on er.role_id = gr.id
    left join general_seniorities as gs on er.seniority_id = gs.id
    where (p.start_date <= oa.effective_date and (p.end_date is null or p.end_date >= oa.end_date))
        and ({{ !employee_ids_filters.value.length }} OR e.id = any({{ employee_ids_filters.value }}) ) 
    	and (({{ show_employees.value }} = 'all') or p.pos_is_active = (case when {{ show_employees.value }} = 'active' then true else false end))
    	and ({{ !filter_by_roles.value.length }} or p.role_id = ANY({{ filter_by_roles.value }}) )
        and ({{ !filter_by_contract_types.value.length }} or p.contract_type_id = ANY({{ filter_by_contract_types.value }}))
        and ({{ !filter_by_cost_center.value.length }} or p.cost_center_id = ANY({{ filter_by_cost_center.value }}))
        and (case
	      when {{ show_type_dates.value }} = 'start_date'
	      	then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
          when {{show_type_dates.value }} = 'end_date'
          	then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
          	else oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}} end)
        and ({{ !filter_by_accounts.value.length }} or oa.account_id = ANY({{ filter_by_accounts.value }}))
		and ({{ !filter_by_account_types.value.length }} or ca.account_type_id = ANY({{ filter_by_account_types.value }}))
        and ({{ !filter_by_managers.value.length }} or ca.manager_id = ANY({{ filter_by_managers.value }}))
)
select pr.seniority, count(pr.ep_id) 
from pr
group by pr.seniority
```

```sql
 with tech as (
	select ep.id, string_agg(t.name, ', ') as tech_stack
    from employee_persons as ep  
    left join employee_technologies as et on ep.id = et.person_id
    left join technologies as t on et.technology_id = t.id 
    group by ep.id
)
, tech2 as (
  	select ep.id, t.name as main_tech
	from employee_persons as ep  
	left join employee_technologies as et on ep.id = et.person_id
	left join technologies as t on et.technology_id = t.id 
	where et.is_principal
)
, positions as (
	select
		ep.id as person_id
		, epos.id
        , er.role_id
  		, epos.employee_role_id
		, epos.contract_type_id
		, epos.cost_center_id
		, epos.start_date
		, epos.end_date
		, epos.effective_date
		, (case when epos.end_date is null then true
			when epos.end_date >= current_date then true
			else false end) as pos_is_active
	from employee_persons ep 
	inner join employee_roles er on er.person_id = ep.id
	inner join employee_positions epos on epos.employee_role_id = er.id
)
, pr as (
   select e.id as ep_id
     , gs.name as seniority
     , gr.name as role 
     , e.first_name
     , e.last_name
     , tech2.main_tech
     , eop.is_available
    from employee_persons as e
    inner join employee_roles as er on er.person_id = e.id
    inner join employee_operational_profiles eop on er.id = eop.employee_role_id 
	inner join operation_assignations oa on oa.operational_profile_id = eop.id
	inner join company_accounts ca on oa.account_id = ca.id
    inner join positions p on er.id = p.employee_role_id

    left join tech on e.id = tech.id
    left join tech2 on e.id = tech2.id
    left join general_roles AS gr on er.role_id = gr.id
    left join general_seniorities as gs on er.seniority_id = gs.id
    where (p.start_date <= oa.effective_date and (p.end_date is null or p.end_date >= oa.end_date))
        and ({{ !employee_ids_filters.value.length }} OR e.id = any({{ employee_ids_filters.value }}) ) 
    	and (({{ show_employees.value }} = 'all') or p.pos_is_active = (case when {{ show_employees.value }} = 'active' then true else false end))
    	and ({{ !filter_by_roles.value.length }} or p.role_id = ANY({{ filter_by_roles.value }}) )
        and ({{ !filter_by_contract_types.value.length }} or p.contract_type_id = ANY({{ filter_by_contract_types.value }}))
        and ({{ !filter_by_cost_center.value.length }} or p.cost_center_id = ANY({{ filter_by_cost_center.value }}))
        and (case
	      when {{ show_type_dates.value }} = 'start_date'
	      	then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
          when {{show_type_dates.value }} = 'end_date'
          	then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
          	else oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}} end)
        and ({{ !filter_by_accounts.value.length }} or oa.account_id = ANY({{ filter_by_accounts.value }}))
		and ({{ !filter_by_account_types.value.length }} or ca.account_type_id = ANY({{ filter_by_account_types.value }}))
        and ({{ !filter_by_managers.value.length }} or ca.manager_id = ANY({{ filter_by_managers.value }}))
        and (case 
          when {{ show_Available.value }} = 'active'   then eop.is_available = true
          when {{ show_Available.value }} = 'inactive' then (eop.is_available =false or eop.is_available is null)
          when {{ show_Available.value }} = 'all'      then true 
        end)
)
select pr.main_tech, count(pr.ep_id) 
from pr
where pr.main_tech is not null 
group by pr.main_tech
order by count desc
LIMIT 6
```

```sql
 with active_employee as (
	select
		ep.id as person_id
		, max(epos.is_active::char(10))::bool as is_active
	from employee_persons ep 
	inner join employee_roles er on er.person_id = ep.id
	inner join employee_positions epos on epos.employee_role_id = er.id
	group by ep.id
)
,bill_cost as (
	select count(1)
		,max(beh.monthly_sales_price) as sales_price
		,max(ceh.real_cost) as real_cost
        ,max(ceh."cost") as "cost"
		,beh.person_id
		,beh.account_id
		,beh.cycle_id
		,concat_ws(' ', max(ep.first_name), max(ep.last_name)) as fullname
        ,eop.is_available is_available
	from bill_employee_history beh
    inner join active_employee ae on ae.person_id = beh.person_id
    inner join general_cycles gc on beh.cycle_id = gc.id
	inner join cost_employee_history ceh on (
		beh.person_id = ceh.person_id
		and beh.cycle_id = ceh.cycle_id 
		and beh.account_id = ceh.account_id)
	inner join employee_persons ep on beh.person_id = ep.id
	inner join company_accounts ca on beh.account_id = ca.id
	left join operation_assignations oa on beh.assignation_id = oa.id
	left join employee_operational_profiles eop on oa.operational_profile_id = eop.id
	left join employee_positions epos on eop.employee_role_id = epos.employee_role_id
	where ({{ !employee_ids_filters.value.length }} OR ep.id = any({{ employee_ids_filters.value }}) ) 
        and ({{ !filter_by_roles.value.length }} or eop.employee_role_id = ANY({{ filter_by_roles.value }}) )
        and ({{ !filter_by_contract_types.value.length }} or epos.contract_type_id = ANY({{ filter_by_contract_types.value }}))
		and ({{ !filter_by_accounts.value.length }} or beh.account_id = ANY({{ filter_by_accounts.value }}))
		and ({{ !filter_by_account_types.value.length }} or ca.account_type_id = ANY({{ filter_by_account_types.value }}))
        and ({{ !filter_by_managers.value.length }} or ca.manager_id = ANY({{ filter_by_managers.value }}) )
        and ({{ !filter_by_cost_center.value.length }} or oa.cost_center_id = ANY({{ filter_by_cost_center.value }}))
        and (({{ show_employees.value }} = 'all') or ae.is_active = (case when {{ show_employees.value }} = 'active' then true else false end))
        and (case when {{ show_type_dates.value }} = 'start_date'
              then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
          when {{show_type_dates.value }} = 'end_date'
              then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
          else oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}} end)
  		and (to_char(gc.start_date, 'yyyy-mm') = {{ filter_date.value }})
	group by beh.assignation_id, beh.person_id, beh.account_id, beh.cycle_id,eop.is_available
)
select sum(sales_price) as revenue
	,avg(sales_price) as avg_revenue
	,sum(sales_price - real_cost) AS profit
	,avg(sales_price - real_cost) as avg_profit
	,sum(real_cost) as real_cost
    ,sum("cost") as "cost"
	,avg(real_cost) as avg_real_cost
	,((sum(sales_price - real_cost))/sum(sales_price)) as margin
from bill_cost
where 
   
 (case 
        when {{ show_Available.value }} = 'active'   then is_available = true
        when {{ show_Available.value }} = 'inactive' then (is_available =false or is_available is null)
        when {{ show_Available.value }} = 'all'      then true end
  )      ;
```
```sql
 with ceh as (
	select
	 ceh.id
	 , ceh.person_id
	 , coalesce(ceh.real_cost, 0) as real_cost
	 , coalesce(ceh.cost, 0) as cost
	 , er.id AS employee_role_id
	 , e.id AS ep_id
	 , gs.name AS seniority
	 , er.role_id 
	 , gr.name AS role 
	 , e.first_name
	 , e.last_name
	from cost_employee_history ceh
	inner join employee_persons as e on ceh.person_id = e.id
	inner join employee_roles as er on er.person_id = e.id    
	inner join general_roles as gr on er.role_id = gr.id
	inner join general_seniorities as gs on er.seniority_id = gs.id
	-- where concat_ws(' ', e.first_name, e.last_name) ilike '%Kamel%'
)
select
	SUM(real_cost)::float as real_cost
	,AVG(real_cost) as avg_real_cost
	,SUM(cost)::float as cost
	,AVG(cost) as avg_cost
from ceh;

```
```sql
 WITH tech AS (SELECT ep.id, string_agg(t.name, ', ') as tech_stack
              FROM employee_persons AS ep  
              LEFT JOIN employee_technologies AS et on ep.id = et.person_id
              LEFT JOIN technologies AS t ON et.technology_id = t.id 
              GROUP BY ep.id
              )
  , tech2 AS (SELECT ep.id, t.name AS main_tech
              FROM employee_persons AS ep  
              LEFT JOIN employee_technologies AS et on ep.id = et.person_id
              LEFT JOIN technologies AS t ON et.technology_id = t.id 
              WHERE et.is_principal
              )
   , langs AS (SELECT ep.id, string_agg(gl.name, ', ') as language_stack
               FROM employee_persons AS ep  
               LEFT JOIN employee_languages AS el on ep.id = el.person_id 
               LEFT JOIN general_languages AS gl on el.language_id = gl.id
               GROUP BY ep.id
              )    
   , pr AS (SELECT 
                  e.id AS ep_id               
                 , e.first_name
                 , e.last_name
                 , git.name AS id_type
                 , e.identification
                 , e.corporate_email
                 , e.address
                 , tech.tech_stack
                 , tech2.main_tech
                 , langs.language_stack
            FROM  employee_persons AS e         
            LEFT JOIN general_document_types AS git    ON e.identification_type_id = git.id
            LEFT JOIN tech                       ON e.id = tech.id
            LEFT JOIN tech2                      ON e.id = tech2.id
            LEFT JOIN langs                      ON e.id = langs.id          
            WHERE ({{ !employee_ids_filters.value.length }} OR e.id = any({{ employee_ids_filters.value }}) ) 
            )
   , ep AS (SELECT ee.id AS employee_position_id
                 , ee.employee_role_id
                 , ee.contract_type_id 
                 , ep.id person_id
                 , gct.name contract_type 
                 , ee.currency
                 , ee.start_date
                 , ee.end_date
                 , ee.salary
                 , CASE WHEN ee.currency = 'COP' THEN ee.cost * {{ factor.value }} 
                                                 ELSE ee.cost
                                                 END AS employee_cost
                 , ee.is_active                 
            FROM  employee_positions AS ee 
            left join general_contract_types gct on 
              ee.contract_type_id = gct.id
            left join employee_roles er on er.id = ee.employee_role_id
            left join employee_persons ep on ep.id = er.person_id
            WHERE 
              (CASE 
                WHEN {{ show_employees.value }} = 'active'   THEN ee.is_active is true
                WHEN {{ show_employees.value }} = 'inactive' THEN ee.is_active is not true
                WHEN {{ show_employees.value }} = 'all'      THEN true
              END) and
            ({{ !filter_by_contract_types.value.length }} OR ee.contract_type_id = ANY({{ filter_by_contract_types.value }}))             
        )
   , oa AS (SELECT oa.operational_profile_id
           , er.person_id
           , eop.employee_role_id as id
           , oa.monthly_sales_price * oa.allocation AS sales_price
           , oa.account_id
           , CASE
              WHEN oa.end_date is null THEN TRUE
              WHEN oa.end_date > NOW() THEN TRUE
              ELSE FALSE
             END AS is_assigned
           , oa.is_billable
           , oa.allocation 
           , ca.account_type_id
           , ca.billing_cycle
           , ca.name
           , oa.end_date
           , oa.effective_date
           , oa.id as operation_assignation_id
           , oa.cost_center_id 
           , gcc.name AS cost_center
           , gr.name role
           , gs.name seniority
           , req.id as employee_quality_id
           , pcu.id::boolean as pcu_id
      FROM operation_assignations oa
      INNER JOIN employee_operational_profiles AS eop ON oa.operational_profile_id = eop.id
      INNER JOIN company_accounts AS ca ON oa.account_id = ca.id
      INNER JOIN general_account_types gat on ca.account_type_id = gat.id 
      LEFT JOIN general_cost_centers as gcc ON oa.cost_center_id = gcc.id
      LEFT JOIN employee_roles AS er ON er.id = eop.employee_role_id
      left join general_roles as gr on er.role_id = gr.id
      LEFT JOIN general_seniorities gs on er.seniority_id = gs.id
      left join pcu_responses pcu on oa.id = pcu.assignation_id and pcu."report_date" between {{ moment(dateCurrent.value).subtract(1, 'M').format('YYYY-MM-DD') }} and coalesce({{dateCurrent.value}}, current_date)
      left join report_employee_quality req on req.assignation_id = oa.id and to_char(req."date", 'YYYY-MM') = to_char(coalesce({{dateCurrent.value}}, current_date), 'YYYY-MM')
      WHERE ({{ !filter_by_accounts.value.length }} OR oa.account_id = ANY({{ filter_by_accounts.value }}) ) 
        AND ({{ !filter_by_account_types.value.length }} OR ca.account_type_id = ANY({{ filter_by_account_types.value }}))
        AND ({{ !filter_by_managers.value.length }} OR ca.manager_id = ANY({{ filter_by_managers.value }}) )
        AND ({{ !filter_by_cost_center.value.length }} OR oa.cost_center_id = ANY({{ filter_by_cost_center.value }}))
        AND ({{ !filter_by_roles.value.length }} OR er.role_id = ANY({{ filter_by_roles.value }}))
        AND (
            CASE WHEN {{ userTypeFilter.value }} = 'Delivery Analyst'
               then (gat."name" in('RPA', 'Software', 'Managed Teams', 'Dedicated-LSS', 'SaaS') OR ca."name" = 'PM')
            WHEN {{ userTypeFilter.value }} = 'Account Manager Lead'
               then gat."name" in('Dedicated')
            ELSE true end
         )
)   
   , oa2 AS (SELECT oa.id
            , SUM(sales_price) AS monthly_sales_price 
            , BOOL_OR(is_assigned) AS is_assigned
            , BOOL_OR(oa.is_billable) AS is_billable
            , SUM(oa.allocation) AS allocation
            , COUNT(id) AS n_accounts
            , STRING_AGG(oa.name, ', ') AS account
            , /*CASE 
                WHEN BOOL_OR(oa.is_billable) THEN NULL 
                ELSE MAX(oa.end_date)
              END AS end_date*/oa.end_date
            , MIN(oa.effective_date) AS effective_date
            , oa.operation_assignation_id
            , oa.cost_center_id
            , oa.cost_center
            , oa.billing_cycle
            , oa.person_id
            , oa.seniority
            , oa.role
            , oa.operation_assignation_id
            , oa.employee_quality_id
            , oa.pcu_id
       FROM oa
       GROUP BY oa.id, oa.operation_assignation_id, oa.cost_center_id, oa.cost_center, oa.billing_cycle, oa.person_id, oa.seniority, oa.role, oa.operation_assignation_id, oa.end_date, oa.employee_quality_id, oa.pcu_id
      )
SELECT * 
FROM pr 
INNER JOIN ep ON pr.ep_id = ep.person_id
INNER JOIN oa2 ON pr.ep_id = oa2.person_id
WHERE (CASE 
          WHEN {{ show_employees.value }} = 'active'   THEN ep.is_active is true
          WHEN {{ show_employees.value }} = 'inactive' THEN ep.is_active is not true
          WHEN {{ show_employees.value }} = 'all'      THEN true
        END)
  AND (case
        when {{ show_type_dates.value }} = 'start_date'
              then ep.start_date >= {{search_by_date.value.start}} and ep.start_date <= {{search_by_date.value.end}}
        when {{show_type_dates.value }} = 'end_date'
              then ep.end_date >= {{search_by_date.value.start}} and ep.end_date <= {{search_by_date.value.end}}
        else oa2.effective_date >= {{search_by_date.value.start}} and oa2.effective_date <= {{search_by_date.value.end}} end)
  AND
      /*ep.is_active = true AND*/
     (CASE WHEN {{show_employees.value}} = 'active' THEN oa2.end_date is null
           WHEN {{show_employees.value}} = 'inactive' THEN oa2.end_date is not null
           WHEN {{show_employees.value}} = 'all' THEN true
      END)


```
```sql
 WITH employee_info as (select                             
                             gcc.id as cost_center_id
                           , gcc.name as cost_center
                           , gpal.id as p_l_id
                           , gpal.name as p_l_category
                        from general_cost_centers gcc 
                        left join general_profit_and_loss gpal on gcc.profit_loss_id = gpal.id
                        )
   , pr AS (SELECT er.id AS employee_role_id
                 , e.id AS ep_id                
                 , gr.name AS role 
                , concat_ws(' ', e.first_name, e.last_name) as employee_name                 
            FROM  employee_persons AS e
            FULL OUTER JOIN employee_roles AS er ON er.person_id = e.id           
            LEFT JOIN general_roles AS gr        ON er.role_id = gr.id         
            WHERE ({{ !employee_ids_filters.value.length }} OR e.id = any({{ employee_ids_filters.value }}) ) 
              AND ({{ !filter_by_roles.value.length }} OR er.role_id = ANY({{ filter_by_roles.value }}) )
            )
   , ep AS (SELECT ee.id AS employee_position_id
                 , ee.employee_role_id
                 , ee.contract_type_id                
                 , ee.currency
                 , ee.start_date
                 , ee.end_date
                 , ee.salary
                 , CASE WHEN ee.currency = 'COP' THEN ee.cost * {{ factor.value }} 
                                                 ELSE ee.cost
                                                 END AS employee_cost
                 , ee.is_active
            FROM  employee_positions AS ee
            LEFT JOIN general_contract_types AS gct ON ee.contract_type_id = gct.id            
           
            WHERE ({{ !filter_by_contract_types.value.length }} OR ee.contract_type_id = ANY({{ filter_by_contract_types.value }}))             
          )
   , oa AS (SELECT oa.operational_profile_id
           , eop.employee_role_id         
           , oa.monthly_sales_price * oa.allocation AS sales_price
           , case when oa.end_date is null
        		then DATE_PART('year', AGE(current_date, oa.start_date))
        		else DATE_PART('year', AGE(oa.end_date, oa.start_date))
      		end as years_ago
      	   , case when oa.end_date is null
        		then DATE_PART('month', AGE(current_date, oa.start_date))
        		else DATE_PART('month', AGE(oa.end_date, oa.start_date))
      		end as months_ago
           , oa.account_id
           , CASE WHEN oa.end_date is null THEN TRUE
                            ELSE CASE WHEN oa.end_date > NOW() THEN TRUE
                                              ELSE FALSE
                                              END 
                            END AS is_assigned
           , oa.is_billable         
           , oa.allocation 
           , ca.account_type_id
           , ca.name
          , oa.start_date
          , oa.end_date
          , oa.effective_date
          , ca.billing_cycle
          , gs.name silo_name
          , ei.cost_center
          , ei.p_l_category
      FROM operation_assignations oa
      LEFT JOIN employee_operational_profiles AS eop ON oa.operational_profile_id = eop.id
      LEFT JOIN company_accounts              AS ca  ON oa.account_id = ca.id
      LEFT JOIN employee_info as ei ON oa.cost_center_id = ei.cost_center_id
      LEFT JOIN general_silos gs on oa.silo_id = gs.id
      WHERE ({{ !filter_by_accounts.value.length }} OR oa.account_id = ANY({{ filter_by_accounts.value }}) ) 
        AND ({{ !filter_by_account_types.value.length }}    OR ca.account_type_id = ANY({{ filter_by_account_types.value }}))
        AND ({{ !filter_by_managers.value.length }} OR ca.manager_id = ANY({{ filter_by_managers.value }}) )
        AND ({{ !filter_by_cost_center.value.length }} OR oa.cost_center_id = ANY({{ filter_by_cost_center.value }}))
      ) 
SELECT *
     , case when (years_ago = 0 and months_ago >= 11 and months_ago <= 13) then sales_price * 1.035
    	when (years_ago = 1 and (months_ago = 0 or months_ago = 1)) then sales_price * 1.035
    	else 0 end as next_sale_price
     , (oa.sales_price - (ep.employee_cost * oa.allocation)) AS profit
     , CASE WHEN oa.sales_price > 0 THEN (oa.sales_price - (ep.employee_cost * oa.allocation))/oa.sales_price
                                    ELSE NULL
                                    END as margin
FROM pr 
LEFT JOIN ep ON pr.employee_role_id = ep.employee_role_id
LEFT JOIN oa ON pr.employee_role_id = oa.employee_role_id
WHERE (CASE 
          WHEN {{ show_employees.value }} = 'active'   THEN ep.is_active is TRUE
          WHEN {{ show_employees.value }} = 'inactive' THEN ep.is_active is FALSE
          WHEN {{ show_employees.value }} = 'all'      THEN true
        END)
    AND (case
        when {{ show_type_dates.value }} = 'start_date'
              then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
        when {{show_type_dates.value }} = 'end_date'
              then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
        else oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}} end)
```
```sql
 with
positions as (
	select ep.id as employee_id
		, epos.id as position_id
		, epos.cost
        , epos.salary
        , epos.bonus
		, er.id as role_id
		, epos.start_date
		, epos.effective_date
		, epos.end_date
		, epos.contract_type_id
        , epos.silo_id
        , ep.corporate_email
        , epos.currency 
		, (case when (epos.end_date is null OR epos.end_date >= current_date ) then true else false end) as is_active
        , epmanager.id as silo_manager_id
        , concat_ws(' ', epmanager.first_name, epmanager.last_name) as silo_manager_name
        , epmanager.corporate_email as silo_manager_email
        , epleader.id as silo_lead_id
        , concat_ws(' ', epleader.first_name, epleader.last_name) as silo_lead_name
        , epleader.corporate_email as silo_lead_email
        , epgleader.id as silo_grandlead_id
        , concat_ws(' ', epgleader.first_name, epgleader.last_name) as silo_grandlead_name
        , epgleader.corporate_email as silo_grandlead_email
	from employee_persons ep 
	inner join employee_roles er on ep.id = er.person_id
	inner join employee_positions epos on er.id = epos.employee_role_id
    left join general_silos gsi on gsi.id = epos.silo_id
    left join general_silos gs_parent on gs_parent.id = gsi.report_to_silo_id 
    left join general_silos gs_grandfather on gs_grandfather.id = gs_parent.report_to_silo_id
    -- silo
    left join employee_operational_profiles eopmanager on eopmanager.id = gsi.manager_id
    left join employee_roles ermanager on ermanager.id = eopmanager.employee_role_id 
    left join employee_persons epmanager on epmanager.id = ermanager.person_id
    -- parent silo
    left join employee_operational_profiles eopleader on eopleader.id = gs_parent.manager_id
    left join employee_roles erleader on erleader.id = eopleader.employee_role_id 
    left join employee_persons epleader on epleader.id = erleader.person_id 
    -- grandfather silo
    left join employee_operational_profiles eopgleader on eopgleader.id = gs_grandfather.manager_id
    left join employee_roles ergleader on ergleader.id = eopgleader.employee_role_id 
    left join employee_persons epgleader on epgleader.id = ergleader.person_id
    where epos.deleted_at is null and
		(to_char(epos.effective_date, 'yyyy-mm') <= {{ filter_date.value }} and
		(epos.end_date is null or (to_char(epos.end_date, 'yyyy-mm') >= {{ filter_date.value }})))
),
ranked_assignations as (
  select 
    ep.id person_id
    , oa.account_id
    , oa.start_date 
    , oa.effective_date 
    , oa.monthly_sales_price
    , lag(oa.monthly_sales_price) 
        over (partition by ep.id, oa.account_id, oa.start_date order by oa.effective_date) previous_monthly_sales_price
    , lag(oa.effective_date)
        over (partition by ep.id, oa.account_id, oa.start_date order by oa.effective_date) previous_effective_date
  from employee_persons ep 
  inner join employee_roles er on er.person_id = ep.id 
  inner join employee_operational_profiles eop on eop.employee_role_id = er.id 
  inner join operation_assignations oa on 
    oa.operational_profile_id = eop.id and oa.is_billable
)
, last_increase_cte as (
  select 
    person_id
    , account_id
    , start_date
    , effective_date
    , monthly_sales_price
        , previous_monthly_sales_price
    , case
        when previous_monthly_sales_price is not null and monthly_sales_price > previous_monthly_sales_price
          then effective_date
          else null
      end increase_date
  from ranked_assignations
)
, final_query as (
  select
    person_id
    , account_id
    , start_date
    , effective_date
    , monthly_sales_price
        , previous_monthly_sales_price 
    , max(increase_date)
        over(partition by person_id, start_date order by effective_date
          rows between unbounded preceding and current row
        ) last_increase_date
  from last_increase_cte
)
, last_client_increase as (
  select
    distinct on (person_id, account_id)
    person_id
    , account_id
   -- , last_increase_date
    --  , effective_date
      , start_date
     , (coalesce(last_increase_date, start_date) + interval '1 year')::date next_increase_date
  from final_query
  order by person_id, account_id, effective_date desc
)
, assignations as (
	select oa.id as assignation_id
		,ca.name as account
        ,ca.account_type_id
		,ca.manager_id
		,gat.name as account_type
		,ca.billing_cycle
		,oa.account_id
		,(oa.monthly_sales_price * oa.allocation)::float as sales_price
		,er.id as role_id
		,concat_ws(' ', ep.first_name, ep.last_name) as fullname
		,ep.id as employee_id
        ,ep.personal_email
		,ep.corporate_email as email
		,ep.phone_number
        ,ep.photo_url
        ,ep.address
        ,ep.identification
        ,ep.birth_date 
        ,gc.name as city
        ,gco.name as country
        ,gna.name as nacionality
        ,gdt.name as identification_type 
		,gs.name as seniority
		,gr.name as role
		,oa.is_billable
        ,oa.cost_center_id
		,oa.allocation
		,oa.start_date
		,oa.effective_date::timestamp
        , lci.next_increase_date sugg_next_price_date
		,oa.end_date
		,oa.monthly_sales_price
		,gcc.name as cost_center
		,gpal.name as p_l_category
		,gsi.name silo_name
        , epp2.id as account_manager_id
        , concat( epp2.first_name,' ' ,epp2.last_name) account_manager_name
        , epp2.corporate_email as account_manager_email
	from employee_persons ep 
	inner join employee_roles er on ep.id = er.person_id
	inner join general_roles gr on er.role_id = gr.id
	inner join general_seniorities gs on er.seniority_id = gs.id 
	inner join employee_operational_profiles eop on er.id = eop.employee_role_id 
	inner join operation_assignations oa on oa.operational_profile_id = eop.id
	inner join company_accounts ca on oa.account_id = ca.id
    left join employee_operational_profiles eop2 on eop2.id= ca.manager_id
    left join employee_roles er2 on er2.id = eop2.employee_role_id
    left join employee_persons epp2 on epp2.id = er2.person_id
	inner join general_account_types gat on ca.account_type_id = gat.id
    inner join general_account_categories gac on ca.account_category_id = gac.id
	inner join general_cost_centers gcc on oa.cost_center_id = gcc.id
	inner join general_profit_and_loss gpal on gcc.profit_loss_id = gpal.id
    left join general_cities gc ON ep.city_id = gc.id
    left join general_countries gco on gc.country_id = gco.id
    left join general_countries gna on ep.nationality_id = gna.id
    left join general_document_types gdt on ep.identification_type_id = gdt.id
    left join general_silos gsi on oa.silo_id = gsi.id
    left join last_client_increase lci on
      lci.person_id = ep.id
      and lci.account_id = oa.account_id
      and lci.start_date = oa.start_date
    where (
		to_char(oa.effective_date, 'yyyy-mm') <= {{ filter_date.value }} 
		and (oa.end_date is null or (to_char(oa.end_date, 'yyyy-mm') >= {{ filter_date.value }}))
	) and 
	(case
		when {{ show_type_dates.value }} = 'start_date'
			then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
		when {{show_type_dates.value }} = 'end_date'
			then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
		else oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}} end
	)
    and (
        CASE WHEN {{ userTypeFilter.value }} = 'Delivery Analyst'
           then (gat."name" = ANY({{ var_account_type.value }}))
        WHEN {{ userTypeFilter.value }} = 'Account Manager Lead'
           then gat."name" = ANY({{ var_account_type.value }})
        ELSE true end
     )
    and (
        CASE WHEN {{ userTypeFilter.value }} = 'Account Manager Lead' AND gat.name = 'Augmented Services'
            then gac.name IN('Account', 'Project')
        ELSE true end
    )
),
accounts_annual_increase as (
  select
    gm.account_id
   -- , gm.value
    , case
      when gm.value  ~ '^[0-9]+(\.[0-9]+)?%$'
        then (replace(gm.value , '%', '')::numeric / 100)
      when gm.value  ~ '^[0-9]+(\.[0-9]+)?$'
        then (gm.value::numeric / 100)
    else null
    end as increased_value
  from governance_models gm
  inner join general_governance_concepts ggc on
    gm.concept_id = ggc.id
    and ggc."name" = 'Anual Increase'
)
, posi_assig as (
	select a.*
		,p.position_id
        ,p.salary
        ,p.bonus
		,p.cost::float as employee_cost
		,p.is_active
		,p.end_date as position_end_date
        ,p.silo_id
        ,p.currency
        ,p.contract_type_id
        , a.sugg_next_price_date next_sale_price_date
        , a.sales_price * (1 + coalesce(aai.increased_value, 0)) as next_sale_price
        ,   case
          when aai.increased_value notnull then round((aai.increased_value * 100), 1) || '% ' || 'annual increase'
          else 'Without info'
          end as next_sale_price_caption
		, (a.sales_price - (p.cost * a.allocation)) AS profit
		, case when a.sales_price > 0 then (a.sales_price - (p.cost * a.allocation)) / a.sales_price else 0
			end as margin
        -- get manager name
        , case when (a.account = 'Dedicated' and p.silo_manager_email <> p.corporate_email) then p.silo_manager_name
          when a.account_manager_email <> p.corporate_email then a.account_manager_name
            when p.silo_manager_email <> p.corporate_email then p.silo_manager_name
            else p.silo_lead_name
          end as manager
        -- get AML name
       , case when (a.account = 'Dedicated' and p.silo_manager_email = p.corporate_email) then p.silo_grandlead_name
      	  when (a.account = 'Dedicated' and p.silo_lead_email <> p.corporate_email) then p.silo_lead_name
      	  when p.silo_manager_email <> p.corporate_email then p.silo_manager_name
        	  when p.silo_lead_email <> p.corporate_email then p.silo_lead_name
            else p.silo_grandlead_name
          end as manager_lead
        -- get manager email
        , case when (a.account = 'Dedicated' and p.silo_manager_email <> p.corporate_email) then p.silo_manager_email 
      	  when a.account_manager_email <> p.corporate_email then a.account_manager_email
        	  when p.silo_manager_email <> p.corporate_email then p.silo_manager_email
        	  else p.silo_lead_email
          end as manager_email
        -- get AML email
        , case when (a.account = 'Dedicated' and p.silo_manager_email = p.corporate_email) then p.silo_grandlead_email
      	  when (a.account = 'Dedicated' and p.silo_lead_email <> p.corporate_email) then p.silo_lead_email
      	  when p.silo_manager_email <> p.corporate_email then p.silo_manager_email
        	  when p.silo_lead_email <> p.corporate_email then p.silo_lead_email
            else p.silo_grandlead_email
          end as manager_lead_email
        -- get Manager Id
        , case when (a.account = 'Dedicated' and p.silo_manager_email <> p.corporate_email) then p.silo_manager_id
      	  when a.account_manager_email <> p.corporate_email then a.account_manager_id
        	  when p.silo_manager_email <> p.corporate_email then p.silo_manager_id
        	  else p.silo_lead_id
          end as manager_id
        -- get AML Id
        , case when (a.account = 'Dedicated' and p.silo_manager_email = p.corporate_email) then p.silo_grandlead_id
      	  when (a.account = 'Dedicated' and p.silo_lead_email <> p.corporate_email) then p.silo_lead_id
      	  when p.silo_manager_email <> p.corporate_email then p.silo_manager_id
        	  when p.silo_lead_email <> p.corporate_email then p.silo_lead_id
            else p.silo_grandlead_id
          end as manager_lead_id
         -- silo_manager_id, silo_lead_id, silo_grandlead_id
	from assignations a 
	inner join positions p on p.employee_id = a.employee_id
    left join accounts_annual_increase aai on aai.account_id = a.account_id and aai.increased_value notnull
    where (
    		p.effective_date <= a.effective_date and 
    		a.effective_date <= p.end_date and
    		(a.end_date is null OR p.end_date <= a.end_date)
    )
    	OR (
    		a.effective_date <= p.effective_date and
    		p.effective_date <= a.end_date and 
    		(p.end_date is null OR p.end_date <= a.end_date)
    )   OR (
    		a.effective_date <= p.effective_date and
    		p.effective_date <= a.end_date and 
    		(p.end_date is null OR p.end_date >= a.end_date)
    )	OR (
    		p.effective_date <= a.effective_date and 
    		(p.end_date is null or p.end_date >= a.end_date)
    )	OR (
    	a.effective_date <= p.effective_date and
    	(a.end_date is null OR p.end_date <= a.end_date)
    )
)
select *
from posi_assig
where 
(case 
	when {{ show_employees.value }} = 'active'   then is_active is true
	when {{ show_employees.value }} = 'inactive' then is_active is false
	when {{ show_employees.value }} = 'all'      then true end
)
order by account_id, fullname;
```
```sql
 with
tech as (
    select ep.id, string_agg(t.name, ', ') as tech_stack
    from employee_persons as ep  
    left join employee_technologies as et on ep.id = et.person_id
    left join technologies as t ON et.technology_id = t.id 
    group by ep.id
),
talent_partner as (
  SELECT
  id,
  concat(first_name,' ',last_name) as full_name,
  corporate_email
FROM company_talent_partners
),
tech_partner as (
  SELECT 
  ctp.id,
  ctp.is_active,
  concat(epe.first_name,' ',epe.last_name) full_name,
  epe.corporate_email
  FROM company_tech_partners as ctp
  LEFT JOIN employee_persons AS epe on 
  ctp.person_id = epe.id
),  
pcu_current_month as (
  select 
    distinct on (er.person_id, oa.account_id)
    pr.id
    , oa.account_id
    , er.person_id
  from pcu_responses pr
  inner join operation_assignations oa on 
    pr.assignation_id = oa.id 
  inner join employee_operational_profiles eop on 
    oa.operational_profile_id = eop.id 
  inner join employee_roles er on 
    eop.employee_role_id = er.id
  where
    to_char(pr.report_date, 'YYYY-MM') = to_char(current_date, 'YYYY-MM')
),
langs as (
    select ep.id, string_agg(concat_ws(' ', gl.name, gll.name), ', ') as language_stack
    from employee_persons as ep  
    left join employee_languages as el on ep.id = el.person_id 
    left join general_languages as gl on el.language_id = gl.id
    left join general_language_levels gll on el.language_level_id = gll.id
    group by ep.id
),
performance_review_month as (
  select 
    distinct on (er.person_id)
    req.id as id
    , er.person_id
  from report_employee_quality req
  inner join operation_assignations oa on req.assignation_id = oa.id 
  inner join employee_operational_profiles eop on oa.operational_profile_id = eop.id 
  inner join employee_roles er on eop.employee_role_id = er.id
  where to_char(req."date", 'YYYY-MM') = to_char(coalesce(current_date), 'YYYY-MM')
  order by er.person_id, req.id desc
),
positions as (
	select ep.corporate_email
		, ep.first_name
		, ep.last_name
        , ep.personal_email
		, gcc.name as cost_center
       	, gct.name as contract_type
       	, case when epos.currency = 'COP'
       		then epos.cost * {{ factor.value }} 
       		else epos.cost end as employee_cost
       	, epos.salary
        , epos.currency
        , ep.address
        , ep.identification
        , ep.identification_type_id
        , ep.birth_date
        , ep.phone_number
        , ep.city_id
        , gc.country_id
       	, epos.start_date
       	, epos.effective_date
        , epos.end_date
        , epos.silo_id
        , tech.tech_stack
        , langs.language_stack
		, er.role_id
		, ep.id
        , gpal.name as profit_and_lost
        , gsi."name" as silo
        , epmanager.id as silo_manager_id
        , concat_ws(' ', epmanager.first_name, epmanager.last_name) as silo_manager_name
        , epmanager.corporate_email as silo_manager_email
        , epleader.id as silo_lead_id
        , concat_ws(' ', epleader.first_name, epleader.last_name) as silo_lead_name
        , epleader.corporate_email as silo_lead_email
        , epgleader.id as silo_grandlead_id
        , concat_ws(' ', epgleader.first_name, epgleader.last_name) as silo_grandlead_name
        , epgleader.corporate_email as silo_grandlead_email
        , gr.name position_role
        , gs.name position_seniority
	from (
		select ep.id, MAX(epos.id) as position_id
		from employee_persons as ep
		inner join employee_roles as er on ep.id = er.person_id
		inner join employee_positions as epos on epos.employee_role_id = er.id
		where epos.deleted_at is null
            and ({{ !employee_ids_filters.value.length }} OR ep.id = any({{ employee_ids_filters.value }}) ) 
			and (case 
                when {{ show_employees.value }} = 'active'   then epos.is_active is true
                when {{ show_employees.value }} = 'inactive' then epos.is_active is not true
                when {{ show_employees.value }} = 'all'      then true end)
            and ({{ !filter_by_contract_types.value.length }} OR epos.contract_type_id = ANY({{ filter_by_contract_types.value }}))
		group by ep.id
	) as posi
	inner join employee_positions as epos on epos.id = posi.position_id
	inner join employee_roles as er on epos.employee_role_id = er.id
	inner join employee_persons as ep on er.person_id = ep.id
    left join general_cities gc on gc.id = ep.city_id
    left join general_roles as gr on er.role_id = gr.id
    left join general_seniorities as gs on er.seniority_id = gs.id
    left join general_cost_centers as gcc on epos.cost_center_id = gcc.id
    left join general_profit_and_loss gpal on gpal.id = gcc.profit_loss_id
    left join general_contract_types as gct on gct.id = epos.contract_type_id
    left join general_silos gsi on gsi.id = epos.silo_id
    left join general_silos gs_parent on gs_parent.id = gsi.report_to_silo_id 
    left join general_silos gs_grandfather on gs_grandfather.id = gs_parent.report_to_silo_id
    -- silo
    left join employee_operational_profiles eopmanager on eopmanager.id = gsi.manager_id
    left join employee_roles ermanager on ermanager.id = eopmanager.employee_role_id 
    left join employee_persons epmanager on epmanager.id = ermanager.person_id
    -- parent silo
    left join employee_operational_profiles eopleader on eopleader.id = gs_parent.manager_id
    left join employee_roles erleader on erleader.id = eopleader.employee_role_id 
    left join employee_persons epleader on epleader.id = erleader.person_id 
    -- grandfather silo
    left join employee_operational_profiles eopgleader on eopgleader.id = gs_grandfather.manager_id
    left join employee_roles ergleader on ergleader.id = eopgleader.employee_role_id 
    left join employee_persons epgleader on epgleader.id = ergleader.person_id
    left join tech on ep.id = tech.id
    left join langs on ep.id = langs.id
    where (case when {{ sw_lss.value }} then true else gpal.name <> 'Dedicated-LSS' end)
), 
assignations as (
	select ep.id
		, oa.id as assignation_id
		, oa.account_id
		, ca.name as account
		, oa.is_billable
		, ca.billing_cycle
        , ca.account_category_id
		, oa.monthly_sales_price * oa.allocation as sales_price
		, oa.allocation
		--, gs."name" as silo
		, gcc."name" as cost_center
		, gpal."name" as profit_loss
        , gr.name as assignation_reason
		, case
          when oa.end_date is null then true
          when oa.end_date >= NOW() then true
          else false
         end as is_assigned
        , coalesce(req.id, 0) as employee_quality_id
        , coalesce(pcu.id, 0) as pcu_id
        , oa.start_date start_date_assignation 
        , tap.full_name as talent_partner
        , tep.full_name as tech_partner
        , epp2.id as account_manager_id
        , concat( epp2.first_name,' ' ,epp2.last_name) account_manager_name
        , epp2.corporate_email as account_manager_email
	from employee_persons as ep
	inner join employee_roles as er on ep.id = er.person_id
	inner join employee_operational_profiles eop on er.id = eop.employee_role_id 
	inner join operation_assignations oa on oa.operational_profile_id = eop.id
	inner join company_accounts ca on oa.account_id = ca.id
    inner join general_account_types gat on ca.account_type_id = gat.id
    inner join general_account_categories gac on ca.account_category_id = gac.id
    left join employee_operational_profiles eop2 on eop2.id= ca.manager_id
    left join employee_roles er2 on er2.id = eop2.employee_role_id
    left join employee_persons epp2 on epp2.id = er2.person_id
    left join general_reasons gr on gr.id= oa.reason_id
	left join talent_partner tap on tap.id = ca.talent_partner_id
    left join tech_partner tep on tep.id = ca.tech_partner_id      
    left join general_cost_centers gcc on gcc.id = oa.cost_center_id
	left join general_profit_and_loss gpal on gpal.id = gcc.profit_loss_id
	left join pcu_current_month pcu on  pcu.person_id = ep.id and pcu.account_id = oa.account_id
    left join performance_review_month req on req.person_id = ep.id
    WHERE ({{ !filter_by_accounts.value.length }} OR oa.account_id = ANY({{ filter_by_accounts.value }}) ) 
        AND ({{ !filter_by_account_types.value.length }} OR ca.account_type_id = ANY({{ filter_by_account_types.value }}))
        AND ({{ !filter_by_cost_center.value.length }} OR oa.cost_center_id = ANY({{ filter_by_cost_center.value }}))
        AND ({{ !filter_by_roles.value.length }} OR er.role_id = ANY({{ filter_by_roles.value }}))
        AND (
            CASE WHEN {{ userTypeFilter.value }} = 'Delivery Analyst'
               then (gat."name" = ANY({{ var_account_type.value }}))
            WHEN {{ userTypeFilter.value }} = 'Account Manager Lead'
               then gat."name" = ANY({{ var_account_type.value }})
            ELSE true end
         )
        AND (
            CASE WHEN {{ userTypeFilter.value }} = 'Account Manager Lead' AND gat.name = 'Augmented Services'
            	then gac.name IN('Account', 'Project')
          	ELSE true end
        )
      AND (case
        when {{ show_type_dates.value }} = 'start_date'
              then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
        when {{show_type_dates.value }} = 'end_date'
              then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
        when {{show_type_dates.value }} = 'effective_date'
	          then oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}}
        else true end)
      AND (case
        when {{show_type_dates.value }} not in ('start_date', 'effective_date', 'end_date')
          then oa.end_date is null or oa.end_date >= current_date
        else true end)
      AND (case 
          when {{ sw_unstarted_positions.value }} = true
            then oa.effective_date <= now()
          else true end
        )
  
), 
accounts as (
	select pos.id
        , max(assi.assignation_id) as assignation_id
        , max(assi.account_category_id) as account_category_id
        , max(employee_quality_id) as employee_quality_id
		, max(pcu_id) as pcu_id
        , max(assi.start_date_assignation) start_date_assignation
		, string_agg(assi.account,  ' | ') as accounts
		, string_agg(case when assi.is_billable then '<input type="checkbox" checked />' else '<input type="checkbox"/>' end, ' ') as billables
        , max(assi.is_billable::varchar)::boolean as is_billable
		, string_agg(TRUNC(assi.sales_price,2)::varchar,  ' | ') as split_sales_prices
        , TRUNC(SUM(assi.sales_price),2) as sales_prices
		, SUM(assi.allocation) as allocations
        , count(1) as count_assignations
        , string_agg(assi.allocation::varchar, ' | ') as split_allocations
        , string_agg(assi.talent_partner,  ' | ') as talent_partner
        , string_agg(assi.tech_partner,  ' | ') as tech_partner
        , assi.assignation_reason as reason
        , assi.account_manager_id
        , assi.account_manager_name
        , assi.account_manager_email
	from positions pos
	inner join assignations assi on pos.id = assi.id
	group by pos.id
      , assi.assignation_reason
      , assi.account_manager_id
      , assi.account_manager_name
      , assi.account_manager_email

)
select 
  distinct on (po.corporate_email)
  po.*
  , ac.*
  -- get manager name
  , case when (ac.accounts = 'Dedicated' and po.silo_manager_email <> po.corporate_email) then po.silo_manager_name
	  when ac.account_manager_email <> po.corporate_email then ac.account_manager_name
  	  when po.silo_manager_email <> po.corporate_email then po.silo_manager_name
  	  else po.silo_lead_name
    end as manager
  -- get AML name
  , case when (ac.accounts = 'Dedicated' and po.silo_manager_email = po.corporate_email) then po.silo_grandlead_name
	  when (ac.accounts = 'Dedicated' and po.silo_lead_email <> po.corporate_email) then po.silo_lead_name
	  when po.silo_manager_email <> po.corporate_email then po.silo_manager_name
  	  when po.silo_lead_email <> po.corporate_email then po.silo_lead_name
      else po.silo_grandlead_name
    end as manager_lead
  -- get manager email
  , case when (ac.accounts = 'Dedicated' and po.silo_manager_email <> po.corporate_email) then po.silo_manager_email 
	  when ac.account_manager_email <> po.corporate_email then ac.account_manager_email
  	  when po.silo_manager_email <> po.corporate_email then po.silo_manager_email
  	  else po.silo_lead_email
    end as manager_email
  -- get AML email
  , case when (ac.accounts = 'Dedicated' and po.silo_manager_email = po.corporate_email) then po.silo_grandlead_email
	  when (ac.accounts = 'Dedicated' and po.silo_lead_email <> po.corporate_email) then po.silo_lead_email
	  when po.silo_manager_email <> po.corporate_email then po.silo_manager_email
  	  when po.silo_lead_email <> po.corporate_email then po.silo_lead_email
      else po.silo_grandlead_email
    end as manager_lead_email
  -- get Manager Id
  , case when (ac.accounts = 'Dedicated' and po.silo_manager_email <> po.corporate_email) then po.silo_manager_id
	  when ac.account_manager_email <> po.corporate_email then ac.account_manager_id
  	  when po.silo_manager_email <> po.corporate_email then po.silo_manager_id
  	  else po.silo_lead_id
    end as manager_id
  -- get AML Id
  , case when (ac.accounts = 'Dedicated' and po.silo_manager_email = po.corporate_email) then po.silo_grandlead_id
	  when (ac.accounts = 'Dedicated' and po.silo_lead_email <> po.corporate_email) then po.silo_lead_id
	  when po.silo_manager_email <> po.corporate_email then po.silo_manager_id
  	  when po.silo_lead_email <> po.corporate_email then po.silo_lead_id
      else po.silo_grandlead_id
    end as manager_lead_id
   -- silo_manager_id, silo_lead_id, silo_grandlead_id
  , eop.id profile_id
  , eop.is_available
  , orr.is_replaced
  , gr.name as role
  , gse.name as seniority
  , sm.profile_match
  , po.position_role
  , po.position_seniority
from positions po
inner join accounts ac on po.id = ac.id
inner join operation_assignations oa on oa.id = ac.assignation_id
inner join employee_operational_profiles eop on eop.id = oa.operational_profile_id
left join employee_roles er on er.id = eop.employee_role_id
left join general_roles as gr on er.role_id = gr.id
left join general_seniorities as gse on er.seniority_id = gse.id
left join operation_resource_releases orr on orr.assignation_id = oa.id
left join employee_skillmatch sm on sm.personal_email = po.personal_email


```
```sql
 with current_position as (
  select 
  	distinct ep.id person_id
  	, first_value(ep2.id) over (partition by ep.id order by ep2.start_date desc, ep2.effective_date desc) position_id	
  from employee_persons ep
  inner join employee_roles er on 
  	er.person_id = ep.id
  inner join employee_positions ep2 on 
  	ep2.employee_role_id = er.id
)  
, assignations as (
  select 
	oa.id	
	, case 
		when extract('day' from oa.start_date) > ca.billing_cycle then 'booking'	
		else 'billable'
	  end	billing_type
  from operation_assignations oa
  inner join company_accounts ca on 
  	oa.account_id = ca.id
  	and ca.billing_cycle notnull
    and oa.is_billable
  inner join employee_operational_profiles eop on 
  	oa.operational_profile_id = eop.id
  inner join employee_roles er on
  	eop.employee_role_id = er.id
  inner join employee_persons ep on
  	er.person_id = ep.id
  inner join current_position cp on 
    cp.person_id = ep.id
  inner join employee_positions ep2 on
    cp.position_id = ep2.id
  left join general_cost_centers gcc on 
    oa.cost_center_id = gcc.id
  left join general_profit_and_loss gpl on
    gcc.profit_loss_id = gpl.id
  where 
    oa.effective_date = oa.start_date 
    and to_char(oa.effective_date, 'YYYY-MM') = {{ date_pl.value.substring(0, 7) }}
    and ({{ !employee_ids_filters.value.length }} OR ep.id = any({{ employee_ids_filters.value }}) ) 
    and ({{ !filter_by_accounts.value.length }} or oa.account_id = ANY({{ filter_by_accounts.value }}))
    and ({{ !filter_by_managers.value.length }} or ca.manager_id = ANY({{ filter_by_managers.value }}))
    and ({{ !filter_by_cost_center.value.length }} or oa.cost_center_id = ANY({{ filter_by_cost_center.value }}))
    and ({{ !filter_by_roles.value.length }} or er.role_id = ANY({{ filter_by_roles.value }}))
    and ({{ !filter_by_account_types.value.length }} or ca.account_type_id = ANY({{ filter_by_account_types.value }}))
    and ({{ !filter_by_contract_types.value.length }} or ep2.contract_type_id = ANY({{ filter_by_contract_types.value }}))
    and (case when {{ sw_lss.value }} = true then true
          else gpl.name <> 'Dedicated-LSS' end)
    and (
      case 
        when {{ show_Available.value }} = 'active'   then eop.is_available = true
        when {{ show_Available.value }} = 'inactive' then (eop.is_available = false or eop.is_available is null)
        when {{ show_Available.value }} = 'all'      then true end
    )
 --    and (
 --      case 
	-- 	when { show_employees.value }} = 'active'   then ep2.is_active is true
	-- 	when { show_employees.value }} = 'inactive' then ep2.is_active is false
	-- 	when { show_employees.value }} = 'all'      then true end
	-- )
    
)
select 
  count(id) filter (where billing_type = 'booking')::int total_booking
  , count(id) filter (where billing_type = 'billable')::int total_billable
from assignations
```

```sql
with current_position as (
  select 
  	distinct ep.id person_id
  	, first_value(ep2.id) over (partition by ep.id order by ep2.start_date desc, ep2.effective_date desc) position_id	
  from employee_persons ep
  inner join employee_roles er on 
  	er.person_id = ep.id
  inner join employee_positions ep2 on 
  	ep2.employee_role_id = er.id
)
select 
  count(distinct ep.id)::int total_leaving
from operation_assignations oa
inner join company_accounts ca on 
  oa.account_id = ca.id
inner join general_reasons gr on 
  oa.end_reason_id = gr.id
  and gr."name" = 'Offboarding'
inner join employee_operational_profiles eop on 
  oa.operational_profile_id = eop.id
inner join employee_roles er on
  eop.employee_role_id = er.id
inner join employee_persons ep on
  er.person_id = ep.id
inner join current_position cp on 
  cp.person_id = ep.id
inner join employee_positions ep2 on
  cp.position_id = ep2.id
left join general_cost_centers gcc on 
  oa.cost_center_id = gcc.id
left join general_profit_and_loss gpl on
  gcc.profit_loss_id = gpl.id
where   	
to_char(oa.end_date, 'YYYY-MM') = {{ date_pl.value.substring(0, 7) }}
and ({{ !employee_ids_filters.value.length }} OR ep.id = any({{ employee_ids_filters.value }}) ) 
and ({{ !filter_by_accounts.value.length }} or oa.account_id = ANY({{ filter_by_accounts.value }}))
and ({{ !filter_by_managers.value.length }} or ca.manager_id = ANY({{ filter_by_managers.value }}))
and ({{ !filter_by_cost_center.value.length }} or oa.cost_center_id = ANY({{ filter_by_cost_center.value }}))
and ({{ !filter_by_roles.value.length }} or er.role_id = ANY({{ filter_by_roles.value }}))
and ({{ !filter_by_account_types.value.length }} or ca.account_type_id = ANY({{ filter_by_account_types.value }}))
and ({{ !filter_by_contract_types.value.length }} or ep2.contract_type_id = ANY({{ filter_by_contract_types.value }}))
and (case when {{ sw_lss.value }} = true then true
      else gpl.name <> 'Dedicated-LSS' end)
and (
  case 
    when {{ show_Available.value }} = 'active'   then eop.is_available = true
when {{ show_Available.value }} = 'inactive' then (eop.is_available = false or eop.is_available is null)
when {{ show_Available.value }} = 'all'      then true end
)
--	 and (
--	   case 
--	 	when { show_employees.value }} = 'active'   then ep2.is_active is true
--	when { show_employees.value }} = 'inactive' then ep2.is_active is false
--	when { show_employees.value }} = 'all'      then true end
--	 ) 
```

```sql
 with numbered_data as (
  select 
    po.id position_id
    , po.employee_role_id
    , ep.id person_id
    , po.effective_date
    , po.salary
    , lag(po.salary,1) over (partition by ep.id order by ep.id, po.effective_date) as previous_salary
  from employee_positions po
  left join employee_roles er on po.employee_role_id = er.id
  left join employee_persons ep on er.person_id = ep.id
  order by ep.id, po.effective_date desc
)
select 
  distinct on (nd.person_id)
  nd.person_id
  , nd.effective_date
from numbered_data nd
where nd.employee_role_id is not null
  and nd.salary > previous_salary
order by nd.person_id, nd.effective_date desc
```

```sql
 SELECT
    TO_CHAR(year_month, 'YYYY-MM') AS year_month,
    COUNT(DISTINCT 
        CASE WHEN                 
            TO_CHAR(ep.start_date, 'YYYY-MM') <= TO_CHAR(df.year_month, 'YYYY-MM') AND 
             TO_CHAR(coalesce(ep.end_date, current_date), 'YYYY-MM') >= TO_CHAR(df.year_month, 'YYYY-MM')
            THEN er.person_id
        END
    )::INT AS employees,
    ARRAY_AGG(DISTINCT er.person_id) AS person_ids
FROM (
    SELECT generate_series AS year_month
    FROM generate_series(
        ('2020-01-01'),
        (SELECT DATE_TRUNC('month', CURRENT_DATE)),
        '1 month'::INTERVAL
    ) AS generate_series
) AS df
CROSS JOIN LATERAL (
    SELECT 
        ep.id,
        epos.start_date,
        epos.end_date,
        epos.employee_role_id
    FROM employee_persons ep
    INNER JOIN employee_roles er ON er.person_id = ep.id
    INNER JOIN employee_positions epos ON epos.employee_role_id = er.id
) ep
LEFT JOIN employee_roles er ON ep.employee_role_id = er.id
WHERE TO_CHAR(ep.start_date, 'YYYY-MM') <= TO_CHAR(df.year_month, 'YYYY-MM') AND 
      (ep.end_date IS NULL OR TO_CHAR(ep.end_date, 'YYYY-MM') >= TO_CHAR(df.year_month, 'YYYY-MM'))
   --   and er.person_id = 34
GROUP BY year_month
ORDER BY year_month ASC;
```

```sql
 SELECT
    to_char(df.year_month, 'YYYY-MM') as year_month,
    count(distinct 
        case when                 
            to_char(ep.position_start_date, 'YYYY-MM') <= to_char(df.year_month, 'YYYY-MM') and 
            to_char(coalesce(ep.position_end_date, current_date), 'YYYY-MM') >= to_char(df.year_month, 'YYYY-MM')
            then ep.employee_id
        end
    )::int AS employees,
    count(distinct
        case when                 
            to_char(ep.position_start_date, 'YYYY-MM') <= to_char(df.year_month, 'YYYY-MM') and 
            to_char(coalesce(ep.position_end_date, current_date), 'YYYY-MM') >= to_char(df.year_month, 'YYYY-MM') and
            ep.is_billable
            then ep.employee_id
        end
    )::int AS billables
from (
    select generate_series as year_month
    from generate_series(
        ('2019-05-01'),
        (select DATE_TRUNC('month', current_date)),
        '1 month'::INTERVAL
    ) as generate_series
) as df
cross join lateral 
(
	with
	positions as (
		select ep.id as employee_id
			,epos.id as position_id
			,er.id as role_id
			,epos.start_date
			,epos.effective_date
			,epos.end_date
			,epos.contract_type_id
            ,gpal.name as profit_and_lost
			,(case when epos.end_date is null then true else false end) as is_active
		from employee_persons ep 
		inner join employee_roles er on ep.id = er.person_id
		inner join employee_positions epos on er.id = epos.employee_role_id
        left join general_cost_centers gcc on gcc.id = epos.cost_center_id
        left join general_profit_and_loss gpal on gpal.id = gcc.profit_loss_id
	    where epos.deleted_at is null
	),
	assignations as (
		select oa.id as assignation_id
	        ,ca.account_type_id
			,oa.account_id
			,er.id as role_id
			,concat_ws(' ', ep.first_name, ep.last_name) as fullname
			,ep.id as employee_id
			,oa.is_billable
	        ,oa.cost_center_id
			,oa.start_date
			,oa.effective_date
			,oa.end_date
            ,ca.manager_id
            ,eop.id as profile_id
            ,eop.is_available 
		from employee_persons ep 
		inner join employee_roles er on ep.id = er.person_id
		inner join employee_operational_profiles eop on er.id = eop.employee_role_id 
		inner join operation_assignations oa on oa.operational_profile_id = eop.id
		inner join company_accounts ca on oa.account_id = ca.id
	    where (case
          when {{ show_type_dates.value }} = 'start_date'
                then oa.start_date >= {{search_by_date.value.start}} and oa.start_date <= {{search_by_date.value.end}}
          when {{show_type_dates.value }} = 'end_date'
                then oa.end_date >= {{search_by_date.value.start}} and oa.end_date <= {{search_by_date.value.end}}
          when {{show_type_dates.value }} = 'effective_date'
  	          then oa.effective_date >= {{search_by_date.value.start}} and oa.effective_date <= {{search_by_date.value.end}}
        else true end)
        and (case 
          when {{ sw_unstarted_positions.value }} = true
            then oa.effective_date <= now()
          else true end
        )
	),
	posi_assig as (
		select a.*
			,p.position_id
			,p.is_active
			,p.end_date as position_end_date
            ,p.start_date as position_start_date
            ,p.contract_type_id
            ,p.profit_and_lost
		from assignations a 
		inner join positions p on p.employee_id = a.employee_id
	    where (
	    		p.effective_date <= a.effective_date and 
	    		a.effective_date <= p.end_date and
	    		(a.end_date is null OR p.end_date <= a.end_date)
	    )
	    	OR (
	    		a.effective_date <= p.effective_date and
	    		p.effective_date <= a.end_date and 
	    		(p.end_date is null OR p.end_date <= a.end_date)
	    )   OR (
	    		a.effective_date <= p.effective_date and
	    		p.effective_date <= a.end_date and 
	    		(p.end_date is null OR p.end_date >= a.end_date)
	    )	OR (
	    		p.effective_date <= a.effective_date and 
	    		(p.end_date is null or p.end_date >= a.end_date)
	    )	OR (
	    	a.effective_date <= p.effective_date and
	    	(a.end_date is null OR p.end_date <= a.end_date)
	    )
	)
	select *
	from posi_assig
	where 
	(case 
		when {{ show_employees.value }} = 'active'   then is_active is true
		when {{ show_employees.value }} = 'inactive' then is_active is false
		when {{ show_employees.value }} = 'all'      then true end
	)
    and (
      case 
        when {{ show_Available.value }} = 'active'   then is_available = true
        when {{ show_Available.value }} = 'inactive' then (is_available = false or is_available is null)
        when {{ show_Available.value }} = 'all'      then true end
    )
    and ({{ !employee_ids_filters.value.length }} OR employee_id = any({{ employee_ids_filters.value }}) ) 
    and ({{ !filter_by_roles.value.length }} or role_id = ANY({{ filter_by_roles.value }}) )
    and ({{ !filter_by_contract_types.value.length }} or contract_type_id = ANY({{ filter_by_contract_types.value }}))
    and ({{ !filter_by_cost_center.value.length }} or cost_center_id = ANY({{ filter_by_cost_center.value }}))
    and ({{ !filter_by_account_types.value.length }} or account_type_id = ANY({{ filter_by_account_types.value }}))
    and ({{ !filter_by_managers.value.length }} or manager_id = ANY({{ filter_by_managers.value }}))
    and ({{ !filter_by_accounts.value.length }} or account_id = ANY({{ filter_by_accounts.value }}))
    and (case when {{ sw_lss.value }} = true then true
          else profit_and_lost <> 'Dedicated-LSS' end)
) ep
group by year_month
order by year_month asc;
```

```sql
 with last_position as (
  select distinct 
  	ero.person_id,
  	first_value(epo.id) over(partition by ero.person_id order by epo.effective_date desc) position_id,
  	first_value(epo.is_active) over(partition by ero.person_id order by epo.effective_date desc) as is_active,
    first_value(epo.contract_type_id) over(partition by ero.person_id order by epo.effective_date desc) as contract_type_id
  from employee_positions as  epo 
  inner join employee_roles as ero on epo.employee_role_id = ero.id
)
SELECT 
  e.id AS person_id
, concat(e.first_name,' ', e.last_name) full_name
, e.personal_email
, e.corporate_email
, gdt.name identification_type
, e.identification    
, e.birth_date
, e.phone_number
, e.address 
, gci.name AS city
, gco.name AS country
, lp.position_id
, lp.is_active
, lp.contract_type_id
FROM  employee_persons AS e
inner join last_position lp on lp.person_id = e.id
LEFT JOIN general_document_types as gdt on gdt.id = e.identification_type_id
LEFT JOIN general_cities as gci on gci.id = e.city_id
LEFT JOIN general_countries as gco on gco.id = gci.country_id
```

```sql
 select ep.id
	, et.knowledge_external_id
	, et.seniority_external_id
from employee_persons ep
inner join employee_technologies et on et.person_id = ep.id
where et.knowledge_external_id is not null
```

```sql
 SELECT id, name FROM general_seniorities
 SELECT id, name FROM general_cost_centers
SELECT id, name FROM general_contract_types
SELECT id, name FROM general_technology_languages
SELECT id, name FROM general_technology_categories

```

```sql
 UPDATE employee_positions
SET is_active = false
WHERE id = {{table3.selectedRow.data.ep_id}}
```

```sql
 SELECT nominal, real, nominal / real as factor
FROM bill_exchange
ORDER BY created_at DESC
```

```sql
 select distinct 
    ep.id
  , concat_ws(' ', first_name, last_name) "name"
  , ep.corporate_email "email"
from employee_persons ep
order by name
```

```sql
 select id, name
from general_document_types
```

```sql
 select id, name, country_id
from general_cities gs
order by gs.name
```


```sql
 select gc.id, gc.name
from general_countries gc
order by gc.name
```


  //general_companies
  //general_cycles
  //general_financial_dimensions