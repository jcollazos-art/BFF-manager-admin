-- Revenue / cost KPIs of the dashboard for one month (:month 'YYYY-MM' = the billing cycle
-- starting that month), from the billing and cost history. One unit per (assignation, cycle):
-- its billed monthly price against the employee's cost on that account in that cycle.
-- Filters: employee_ids, role_ids, contract_type_ids (any position of the assignation's role),
-- account_ids, account_type_ids, manager_ids, cost_center_ids (of the assignation), employees
-- (has an is_active position / has none), date range, availability.
-- Fixes:
--   * role_ids compares general_roles ids with the role's role_id - Retool compared them with
--     employee_role ids, so the role filter matched unrelated rows;
--   * the contract type filter is an EXISTS - Retool joined every position of the role, which
--     the MAX()es hid but cost a join per position;
--   * margin is NULL instead of a division-by-zero error when there is no revenue.
WITH people AS (
    SELECT er.person_id, bool_or(pos.is_active) AS is_active
    FROM employee_roles er
    JOIN employee_positions pos ON pos.employee_role_id = er.id
    GROUP BY er.person_id
),
bill_cost AS (
    SELECT
        max(beh.monthly_sales_price) AS sales_price,
        max(ceh.real_cost) AS real_cost,
        max(ceh.cost) AS cost
    FROM bill_employee_history beh
    JOIN people p ON p.person_id = beh.person_id
    JOIN general_cycles gc ON gc.id = beh.cycle_id
    JOIN cost_employee_history ceh
        ON ceh.person_id = beh.person_id
       AND ceh.cycle_id = beh.cycle_id
       AND ceh.account_id = beh.account_id
    JOIN company_accounts ca ON ca.id = beh.account_id
    LEFT JOIN operation_assignations oa ON oa.id = beh.assignation_id
    LEFT JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
    LEFT JOIN employee_roles er ON er.id = eop.employee_role_id
    WHERE to_char(gc.start_date, 'YYYY-MM') = :month
      AND (CAST(:employee_ids AS int[]) IS NULL OR beh.person_id = ANY(CAST(:employee_ids AS int[])))
      AND (CAST(:role_ids AS int[]) IS NULL OR er.role_id = ANY(CAST(:role_ids AS int[])))
      AND (CAST(:contract_type_ids AS int[]) IS NULL OR EXISTS (
          SELECT 1 FROM employee_positions pos
          WHERE pos.employee_role_id = eop.employee_role_id
            AND pos.contract_type_id = ANY(CAST(:contract_type_ids AS int[]))
      ))
      AND (CAST(:account_ids AS int[]) IS NULL OR beh.account_id = ANY(CAST(:account_ids AS int[])))
      AND (CAST(:account_type_ids AS int[]) IS NULL OR ca.account_type_id = ANY(CAST(:account_type_ids AS int[])))
      AND (CAST(:manager_ids AS int[]) IS NULL OR ca.manager_id = ANY(CAST(:manager_ids AS int[])))
      AND (CAST(:cost_center_ids AS int[]) IS NULL OR oa.cost_center_id = ANY(CAST(:cost_center_ids AS int[])))
      AND (:employees = 'all' OR p.is_active = (:employees = 'active'))
      AND (CAST(:date_from AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) >= CAST(:date_from AS date))
      AND (CAST(:date_to AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) <= CAST(:date_to AS date))
      AND (:availability = 'all' OR coalesce(eop.is_available, false) = (:availability = 'available'))
    GROUP BY beh.assignation_id, beh.person_id, beh.account_id, beh.cycle_id
)
SELECT
    sum(sales_price)::float AS revenue,
    avg(sales_price)::float AS avg_revenue,
    sum(sales_price - real_cost)::float AS profit,
    avg(sales_price - real_cost)::float AS avg_profit,
    sum(real_cost)::float AS real_cost,
    sum(cost)::float AS cost,
    avg(real_cost)::float AS avg_real_cost,
    (sum(sales_price - real_cost) / nullif(sum(sales_price), 0))::float AS margin
FROM bill_cost
