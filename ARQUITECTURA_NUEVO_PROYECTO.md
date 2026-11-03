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

### Track B — Reportería (SQL crudo / Core)

Para pivots, CTEs, agregaciones con `FILTER (WHERE ...)` y dashboards. No se fuerza a pasar por `relationship()`, porque ahí el ORM se vuelve torpe y lento. Va en `reports.py` de cada feature (todavía no existe ninguno), con lista blanca para cualquier identificador dinámico.

**Regla de decisión**:
- ¿"Dame esta entidad (o pocas) con sus relaciones, para mostrar o editar"? → **Track A**.
- ¿"Cuenta, agrega o pivotea muchas filas para un reporte"? → **Track B**.

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
      repository.py       # EmployeeRepository(BaseRepository) - solo consultas propias
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
controller  →  use_cases  →  repository  →  models (ORM)  →  Postgres
   │              │              │
   │              │              └─ ejecuta / hace flush, nunca commit
   │              └─ reglas del caso de uso; convierte Pydantic → dict
   └─ valida entrada (schemas/request), inyecta repo con Depends, envuelve en Envelope/Page
```

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
4. `features/<feature>/repository.py`: `class XRepository(BaseRepository)`, solo con las consultas propias (listado con filtros y `_SORTABLE_FIELDS`, detalle con `selectinload`).
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

  //general_companies
  //general_cycles
  //general_financial_dimensions