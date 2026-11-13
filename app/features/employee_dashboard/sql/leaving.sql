-- Employees leaving in a month (:month 'YYYY-MM'): employees with an assignation ending that
-- month with end reason 'Offboarding'. Same filters as new_assignations.sql, and the same
-- fixes (include_lss keeps assignations without P&L; current position via DISTINCT ON).
WITH current_position AS (
    SELECT DISTINCT ON (er.person_id)
        er.person_id,
        pos.contract_type_id
    FROM employee_positions pos
    JOIN employee_roles er ON er.id = pos.employee_role_id
    ORDER BY er.person_id, pos.start_date DESC NULLS LAST, pos.effective_date DESC NULLS LAST, pos.id DESC
)
SELECT count(DISTINCT er.person_id)::int AS total_leaving
FROM operation_assignations oa
JOIN company_accounts ca ON ca.id = oa.account_id
JOIN general_reasons gr ON gr.id = oa.end_reason_id AND gr.name = 'Offboarding'
JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
JOIN employee_roles er ON er.id = eop.employee_role_id
JOIN current_position cp ON cp.person_id = er.person_id
LEFT JOIN general_cost_centers gcc ON gcc.id = oa.cost_center_id
LEFT JOIN general_profit_and_loss gpl ON gpl.id = gcc.profit_loss_id
WHERE to_char(oa.end_date, 'YYYY-MM') = :month
  AND (CAST(:employee_ids AS int[]) IS NULL OR er.person_id = ANY(CAST(:employee_ids AS int[])))
  AND (CAST(:account_ids AS int[]) IS NULL OR oa.account_id = ANY(CAST(:account_ids AS int[])))
  AND (CAST(:manager_ids AS int[]) IS NULL OR ca.manager_id = ANY(CAST(:manager_ids AS int[])))
  AND (CAST(:cost_center_ids AS int[]) IS NULL OR oa.cost_center_id = ANY(CAST(:cost_center_ids AS int[])))
  AND (CAST(:role_ids AS int[]) IS NULL OR er.role_id = ANY(CAST(:role_ids AS int[])))
  AND (CAST(:account_type_ids AS int[]) IS NULL OR ca.account_type_id = ANY(CAST(:account_type_ids AS int[])))
  AND (CAST(:contract_type_ids AS int[]) IS NULL OR cp.contract_type_id = ANY(CAST(:contract_type_ids AS int[])))
  AND (CAST(:include_lss AS boolean) OR gpl.name IS DISTINCT FROM 'Dedicated-LSS')
  AND (:availability = 'all' OR coalesce(eop.is_available, false) = (:availability = 'available'))
