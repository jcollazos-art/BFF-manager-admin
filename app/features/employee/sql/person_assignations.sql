-- Assignations table of an employee's main view: every assignation paired with each position
-- of the employee it overlaps in time, with the margin. Replaces the Retool
-- "positions x assignations" query, with these fixes:
--   * the catalogs (role, seniority, account, account type, cost center, P&L, silo, financial
--     dimension) are LEFT JOINs - Retool's INNER JOINs dropped an assignation whose cost
--     center had no P&L, whose account had no type, etc.;
--   * Retool's five OR'd date conditions are written as the single overlap test they add up to
--     (inclusive; a missing end_date means still open);
--   * `manager_id` comes once (Retool selected it twice), and `manager` is null, not '', when
--     the account has no manager.
-- Kept from Retool: `is_active` means "the paired position has no end_date" (not the
-- positions.is_active column), and soft-deleted positions are ignored.
WITH positions AS (
    SELECT
        epos.id AS position_id,
        epos.cost,
        epos.salary,
        epos.effective_date,
        epos.end_date
    FROM employee_positions epos
    JOIN employee_roles er ON er.id = epos.employee_role_id
    WHERE er.person_id = :person_id
      AND epos.deleted_at IS NULL
),
assignations AS (
    SELECT
        oa.id AS assignation_id,
        oa.account_id,
        ca.name AS account,
        ca.account_type_id,
        gat.name AS account_type,
        ca.billing_cycle,
        ca.manager_id,
        nullif(concat_ws(' ', ep_manager.first_name, ep_manager.last_name), '') AS manager,
        er.id AS role_id,
        er.person_id AS employee_id,
        gr.name AS role,
        gs.name AS seniority,
        oa.is_billable,
        oa.allocation,
        oa.monthly_sales_price,
        oa.monthly_sales_price * oa.allocation AS sales_price,
        oa.start_date,
        oa.effective_date,
        oa.end_date,
        oa.po_number,
        oa.cost_center_id,
        gcc.name AS cost_center,
        gpal.name AS p_l_category,
        gsi.name AS silo_name,
        gfd.name AS financial_dimension
    FROM employee_roles er
    JOIN employee_operational_profiles eop ON eop.employee_role_id = er.id
    JOIN operation_assignations oa ON oa.operational_profile_id = eop.id
    LEFT JOIN general_roles gr ON gr.id = er.role_id
    LEFT JOIN general_seniorities gs ON gs.id = er.seniority_id
    LEFT JOIN company_accounts ca ON ca.id = oa.account_id
    LEFT JOIN general_account_types gat ON gat.id = ca.account_type_id
    LEFT JOIN general_cost_centers gcc ON gcc.id = oa.cost_center_id
    LEFT JOIN general_profit_and_loss gpal ON gpal.id = gcc.profit_loss_id
    LEFT JOIN general_silos gsi ON gsi.id = oa.silo_id
    LEFT JOIN general_financial_dimensions gfd ON gfd.id = oa.financial_dimension_id
    -- company_accounts.manager_id is an operational profile id
    LEFT JOIN employee_operational_profiles eop_manager ON eop_manager.id = ca.manager_id
    LEFT JOIN employee_roles er_manager ON er_manager.id = eop_manager.employee_role_id
    LEFT JOIN employee_persons ep_manager ON ep_manager.id = er_manager.person_id
    WHERE er.person_id = :person_id
)
SELECT
    a.*,
    p.position_id,
    p.salary,
    p.cost AS employee_cost,
    p.end_date IS NULL AS is_active,
    p.end_date AS position_end_date,
    CASE
        WHEN a.is_billable AND a.sales_price > 0 THEN (a.sales_price - p.cost) / a.sales_price
        ELSE 0
    END AS margin
FROM assignations a
JOIN positions p
  ON p.effective_date <= coalesce(a.end_date, 'infinity'::date)
 AND a.effective_date <= coalesce(p.end_date, 'infinity'::date)
ORDER BY is_active DESC, a.start_date DESC, a.effective_date DESC, a.assignation_id DESC, p.position_id DESC
