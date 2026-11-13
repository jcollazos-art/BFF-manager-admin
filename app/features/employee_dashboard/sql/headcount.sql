-- Headcount chart of the dashboard, per month since 2019-05: employees, and billable
-- employees, with an (assignation, position) pair whose position covers the month. Pairs are
-- an assignation and a position of the same employee that overlap in time; the filters apply
-- to the pairs.
-- Filters: date range (only when date_field is given), only_started, employees (position
-- without end_date / with one), availability, employee_ids, role_ids, contract_type_ids (of
-- the position), cost_center_ids (of the assignation), account_type_ids, manager_ids,
-- account_ids, include_lss (P&L of the position's cost center).
-- Fixes:
--   * the pairs are built once - Retool rebuilt them in a CROSS JOIN LATERAL for every month,
--     though they don't depend on the month;
--   * role_ids compares general_roles ids with the role's role_id (Retool: employee_role id);
--   * Retool's five OR'd date conditions are the single overlap test they add up to
--     (inclusive; a missing end_date means still open);
--   * include_lss=false hides only the 'Dedicated-LSS' P&L (Retool's `<>` dropped positions
--     without P&L too).
WITH pairs AS (
    SELECT
        er.person_id,
        oa.is_billable,
        pos.start_date AS position_start_date,
        pos.end_date AS position_end_date
    FROM employee_roles er
    JOIN employee_operational_profiles eop ON eop.employee_role_id = er.id
    JOIN operation_assignations oa ON oa.operational_profile_id = eop.id
    JOIN company_accounts ca ON ca.id = oa.account_id
    JOIN employee_roles pos_role ON pos_role.person_id = er.person_id
    JOIN employee_positions pos
        ON pos.employee_role_id = pos_role.id
       AND pos.deleted_at IS NULL
       AND pos.effective_date <= coalesce(oa.end_date, 'infinity'::date)
       AND oa.effective_date <= coalesce(pos.end_date, 'infinity'::date)
    LEFT JOIN general_cost_centers gcc ON gcc.id = pos.cost_center_id
    LEFT JOIN general_profit_and_loss gpal ON gpal.id = gcc.profit_loss_id
    WHERE (CAST(:date_field AS text) IS NULL OR (
              (CAST(:date_from AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
                   WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) >= CAST(:date_from AS date))
          AND (CAST(:date_to AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
                   WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) <= CAST(:date_to AS date))))
      AND (NOT CAST(:only_started AS boolean) OR oa.effective_date <= current_date)
      AND (:employees = 'all' OR (pos.end_date IS NULL) = (:employees = 'active'))
      AND (:availability = 'all' OR coalesce(eop.is_available, false) = (:availability = 'available'))
      AND (CAST(:employee_ids AS int[]) IS NULL OR er.person_id = ANY(CAST(:employee_ids AS int[])))
      AND (CAST(:role_ids AS int[]) IS NULL OR er.role_id = ANY(CAST(:role_ids AS int[])))
      AND (CAST(:contract_type_ids AS int[]) IS NULL OR pos.contract_type_id = ANY(CAST(:contract_type_ids AS int[])))
      AND (CAST(:cost_center_ids AS int[]) IS NULL OR oa.cost_center_id = ANY(CAST(:cost_center_ids AS int[])))
      AND (CAST(:account_type_ids AS int[]) IS NULL OR ca.account_type_id = ANY(CAST(:account_type_ids AS int[])))
      AND (CAST(:manager_ids AS int[]) IS NULL OR ca.manager_id = ANY(CAST(:manager_ids AS int[])))
      AND (CAST(:account_ids AS int[]) IS NULL OR oa.account_id = ANY(CAST(:account_ids AS int[])))
      AND (CAST(:include_lss AS boolean) OR gpal.name IS DISTINCT FROM 'Dedicated-LSS')
)
SELECT
    to_char(m.month, 'YYYY-MM') AS year_month,
    count(DISTINCT p.person_id)::int AS employees,
    count(DISTINCT p.person_id) FILTER (WHERE p.is_billable)::int AS billables
FROM generate_series(DATE '2019-05-01', date_trunc('month', current_date), INTERVAL '1 month') AS m(month)
LEFT JOIN pairs p
    ON date_trunc('month', p.position_start_date) <= m.month
   AND date_trunc('month', coalesce(p.position_end_date, current_date)) >= m.month
GROUP BY m.month
ORDER BY m.month
