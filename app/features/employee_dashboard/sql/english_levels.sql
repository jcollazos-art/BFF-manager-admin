-- English level distribution of the dashboard: employees per English level ('Others' = no
-- English level registered). An employee counts when an assignation of theirs matches the
-- filters and lies within a position of the same role (position started on or before the
-- assignation's effective date and doesn't end before the assignation does).
-- Filters: employee_ids, employees (position not ended / ended), role_ids, contract_type_ids
-- and cost_center_ids (of the position), date range, account_ids, account_type_ids, manager_ids.
-- Fix: counts employees. Retool counted rows - one per (assignation, matching position,
-- English entry) - so an employee with three assignations weighed three.
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
),
english AS (
    SELECT DISTINCT ON (el.person_id)
        el.person_id,
        gll.name AS level
    FROM employee_languages el
    JOIN general_languages gl ON gl.id = el.language_id AND gl.name = 'English'
    LEFT JOIN general_language_levels gll ON gll.id = el.language_level_id
    ORDER BY el.person_id, el.id DESC
)
SELECT
    coalesce(e.level, 'Others') AS english_level,
    count(*)::int AS employees
FROM matched m
LEFT JOIN english e ON e.person_id = m.person_id
GROUP BY 1
ORDER BY employees DESC, english_level
