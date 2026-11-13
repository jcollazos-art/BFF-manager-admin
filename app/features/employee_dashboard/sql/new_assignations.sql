-- New billable assignations of a month (:month 'YYYY-MM'): assignations whose first effective
-- date (effective_date = start_date) falls in the month, on an account with a billing cycle.
-- 'booking' when it started after the account's billing-cycle day, else 'billable'.
-- Filters: employee_ids, account_ids, manager_ids, cost_center_ids (of the assignation),
-- role_ids, account_type_ids, contract_type_ids (of the employee's current position - the
-- latest by start/effective date), include_lss (P&L of the assignation's cost center),
-- availability.
-- Fixes:
--   * include_lss=false hides only the 'Dedicated-LSS' P&L - Retool's `<>` also dropped every
--     assignation without a cost center or P&L;
--   * the current position is picked with DISTINCT ON and an id tiebreaker instead of a
--     first_value() window over every position.
WITH current_position AS (
    SELECT DISTINCT ON (er.person_id)
        er.person_id,
        pos.contract_type_id
    FROM employee_positions pos
    JOIN employee_roles er ON er.id = pos.employee_role_id
    ORDER BY er.person_id, pos.start_date DESC NULLS LAST, pos.effective_date DESC NULLS LAST, pos.id DESC
),
assignations AS (
    SELECT
        oa.id,
        CASE WHEN extract(day FROM oa.start_date) > ca.billing_cycle THEN 'booking' ELSE 'billable' END AS billing_type
    FROM operation_assignations oa
    JOIN company_accounts ca ON ca.id = oa.account_id AND ca.billing_cycle IS NOT NULL
    JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
    JOIN employee_roles er ON er.id = eop.employee_role_id
    JOIN current_position cp ON cp.person_id = er.person_id
    LEFT JOIN general_cost_centers gcc ON gcc.id = oa.cost_center_id
    LEFT JOIN general_profit_and_loss gpl ON gpl.id = gcc.profit_loss_id
    WHERE oa.is_billable
      AND oa.effective_date = oa.start_date
      AND to_char(oa.effective_date, 'YYYY-MM') = :month
      AND (CAST(:employee_ids AS int[]) IS NULL OR er.person_id = ANY(CAST(:employee_ids AS int[])))
      AND (CAST(:account_ids AS int[]) IS NULL OR oa.account_id = ANY(CAST(:account_ids AS int[])))
      AND (CAST(:manager_ids AS int[]) IS NULL OR ca.manager_id = ANY(CAST(:manager_ids AS int[])))
      AND (CAST(:cost_center_ids AS int[]) IS NULL OR oa.cost_center_id = ANY(CAST(:cost_center_ids AS int[])))
      AND (CAST(:role_ids AS int[]) IS NULL OR er.role_id = ANY(CAST(:role_ids AS int[])))
      AND (CAST(:account_type_ids AS int[]) IS NULL OR ca.account_type_id = ANY(CAST(:account_type_ids AS int[])))
      AND (CAST(:contract_type_ids AS int[]) IS NULL OR cp.contract_type_id = ANY(CAST(:contract_type_ids AS int[])))
      AND (CAST(:include_lss AS boolean) OR gpl.name IS DISTINCT FROM 'Dedicated-LSS')
      AND (:availability = 'all' OR coalesce(eop.is_available, false) = (:availability = 'available'))
)
SELECT
    count(*) FILTER (WHERE billing_type = 'booking')::int AS total_booking,
    count(*) FILTER (WHERE billing_type = 'billable')::int AS total_billable
FROM assignations
