-- Managers for the "managers" filter of the employees dashboard: people with a Project
-- Manager / Account Manager / Account Manager Lead / Key Account Manager role. The filter
-- compares against company_accounts.manager_id, an operational profile id, so each manager
-- carries `profile_ids` (the profiles of those roles).
-- Same rule as the Retool query: the person needs an active position outside the
-- "Dedicated" silo - except for a Key Account Manager role, which only needs an active
-- position. Fixes:
--   * EXISTS instead of joining every position: Retool's joins multiplied the rows, so
--     `role` and `profile_ids` came with repeated values;
--   * ordered by full name (Retool: first name only).
SELECT
    ep.id,
    concat_ws(' ', ep.first_name, ep.last_name) AS name,
    string_agg(DISTINCT gr.name, ', ') FILTER (WHERE er.is_main) AS role,
    array_agg(DISTINCT eop.id) AS profile_ids
FROM employee_persons ep
JOIN employee_roles er ON er.person_id = ep.id
JOIN general_roles gr ON gr.id = er.role_id
JOIN employee_operational_profiles eop ON eop.employee_role_id = er.id
WHERE gr.name IN ('Project Manager', 'Account Manager', 'Account Manager Lead', 'Key Account Manager')
  AND EXISTS (
      SELECT 1
      FROM employee_roles any_role
      JOIN employee_positions pos ON pos.employee_role_id = any_role.id
      LEFT JOIN general_silos gs ON gs.id = pos.silo_id
      WHERE any_role.person_id = ep.id
        AND pos.is_active
        AND (gr.name = 'Key Account Manager' OR gs.name <> 'Dedicated')
  )
GROUP BY ep.id
ORDER BY name, ep.id
