-- Every employee with personal data (catalog ids resolved to names) and their latest
-- position (by effective_date, across all roles): its id, whether it is active and its
-- contract type. Employees without any position are left out, as in Retool.
-- Fix: DISTINCT ON with `pos.id` as tiebreaker instead of Retool's three first_value()
-- windows - with two positions on the same effective_date those could each pick a
-- different position, mixing its id with another one's is_active/contract type.
WITH last_position AS (
    SELECT DISTINCT ON (er.person_id)
        er.person_id,
        pos.id AS position_id,
        pos.is_active,
        pos.contract_type_id
    FROM employee_positions pos
    JOIN employee_roles er ON er.id = pos.employee_role_id
    ORDER BY er.person_id, pos.effective_date DESC NULLS LAST, pos.id DESC
)
SELECT
    ep.id AS person_id,
    concat_ws(' ', ep.first_name, ep.last_name) AS full_name,
    ep.personal_email,
    ep.corporate_email,
    gdt.name AS identification_type,
    ep.identification,
    ep.birth_date,
    ep.phone_number,
    ep.address,
    gci.name AS city,
    gco.name AS country,
    lp.position_id,
    lp.is_active,
    lp.contract_type_id
FROM employee_persons ep
JOIN last_position lp ON lp.person_id = ep.id
LEFT JOIN general_document_types gdt ON gdt.id = ep.identification_type_id
LEFT JOIN general_cities gci ON gci.id = ep.city_id
LEFT JOIN general_countries gco ON gco.id = gci.country_id
ORDER BY full_name, ep.id
