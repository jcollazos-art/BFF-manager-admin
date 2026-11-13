-- Top 6 main (principal) technologies of the dashboard: employees per principal technology.
-- Same matching and filters as english_levels.sql, plus `availability` (operational profile).
-- Fix: counts employees, not rows (see english_levels.sql).
WITH matched AS (
    SELECT DISTINCT er.person_id
    FROM employee_roles er
    JOIN employee_operational_profiles eop ON eop.employee_role_id = er.id
    JOIN operation_assignations oa ON oa.operational_profile_id = eop.id
    JOIN company_accounts ca ON ca.id = oa.account_id
    JOIN employee_positions pos
        ON pos.employee_role_id = er.id
       AND pos.start_date <= oa.effective_date
       AND (pos.end_date IS NULL OR pos.end_date >= oa.end_date)
    WHERE (CAST(:employee_ids AS int[]) IS NULL OR er.person_id = ANY(CAST(:employee_ids AS int[])))
      AND (:employees = 'all' OR (pos.end_date IS NULL OR pos.end_date >= current_date) = (:employees = 'active'))
      AND (CAST(:role_ids AS int[]) IS NULL OR er.role_id = ANY(CAST(:role_ids AS int[])))
      AND (CAST(:contract_type_ids AS int[]) IS NULL OR pos.contract_type_id = ANY(CAST(:contract_type_ids AS int[])))
      AND (CAST(:cost_center_ids AS int[]) IS NULL OR pos.cost_center_id = ANY(CAST(:cost_center_ids AS int[])))
      AND (CAST(:account_ids AS int[]) IS NULL OR oa.account_id = ANY(CAST(:account_ids AS int[])))
      AND (CAST(:account_type_ids AS int[]) IS NULL OR ca.account_type_id = ANY(CAST(:account_type_ids AS int[])))
      AND (CAST(:manager_ids AS int[]) IS NULL OR ca.manager_id = ANY(CAST(:manager_ids AS int[])))
      AND (CAST(:date_from AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) >= CAST(:date_from AS date))
      AND (CAST(:date_to AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) <= CAST(:date_to AS date))
      AND (:availability = 'all' OR coalesce(eop.is_available, false) = (:availability = 'available'))
)
SELECT
    t.name AS main_tech,
    count(DISTINCT m.person_id)::int AS employees
FROM matched m
JOIN employee_technologies et ON et.person_id = m.person_id AND et.is_principal
JOIN technologies t ON t.id = et.technology_id
GROUP BY t.name
ORDER BY employees DESC, main_tech
LIMIT 6
