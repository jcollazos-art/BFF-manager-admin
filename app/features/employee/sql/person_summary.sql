-- Header of an employee's main view: person data with every catalog id resolved to its name.
-- Replaces the Retool "employee" query, with three fixes:
--   * one row per person, with the roles as a JSON array (Retool returned one row per role);
--   * a person without roles is still returned (Retool's INNER JOINs dropped them);
--   * the technology/language aggregates only read this person's rows (Retool's CTEs
--     aggregated every employee in the table and then joined one).
SELECT
    ep.id AS employee_id,
    concat_ws(' ', ep.first_name, ep.last_name) AS fullname,
    ep.first_name,
    ep.last_name,
    ep.personal_email,
    ep.corporate_email AS email,
    ep.phone_number,
    ep.photo_url,
    ep.address,
    ep.identification,
    ep.birth_date,
    gc.name AS city,
    gco.name AS country,
    gna.name AS nationality,
    gdt.name AS identification_type,
    roles.roles,
    tech.tech_stack,
    tech.main_tech,
    langs.language_stack
FROM employee_persons ep
LEFT JOIN general_cities gc ON gc.id = ep.city_id
LEFT JOIN general_countries gco ON gco.id = gc.country_id
LEFT JOIN general_countries gna ON gna.id = ep.nationality_id
LEFT JOIN general_document_types gdt ON gdt.id = ep.identification_type_id
LEFT JOIN LATERAL (
    SELECT coalesce(
        json_agg(
            json_build_object('id', er.id, 'role', gr.name, 'seniority', gs.name, 'is_main', er.is_main)
            ORDER BY er.is_main DESC NULLS LAST, er.id
        ),
        '[]'
    ) AS roles
    FROM employee_roles er
    LEFT JOIN general_roles gr ON gr.id = er.role_id
    LEFT JOIN general_seniorities gs ON gs.id = er.seniority_id
    WHERE er.person_id = ep.id
) roles ON true
LEFT JOIN LATERAL (
    SELECT
        string_agg(t.name, ', ' ORDER BY et.is_principal DESC NULLS LAST, t.name) AS tech_stack,
        (array_agg(t.name ORDER BY t.name) FILTER (WHERE et.is_principal))[1] AS main_tech
    FROM employee_technologies et
    JOIN technologies t ON t.id = et.technology_id
    WHERE et.person_id = ep.id
) tech ON true
LEFT JOIN LATERAL (
    SELECT string_agg(gl.name, ', ' ORDER BY gl.name) AS language_stack
    FROM employee_languages el
    JOIN general_languages gl ON gl.id = el.language_id
    WHERE el.person_id = ep.id
) langs ON true
WHERE ep.id = :person_id
