-- Assignations table of the dashboard: one row per (position, assignation) pair of an
-- employee - a position and an assignation of the same employee that overlap in time - with
-- personal data, tech/language stacks, cost, sales price and the PCU / performance review
-- around :reference_date.
-- Filters: employee_ids, employees (position is_active and assignation open / position not
-- active and assignation ended), contract_type_ids (position), account_ids, account_type_ids,
-- manager_ids, cost_center_ids, role_ids (assignation), user_type (fixed account types, see
-- below), date range on the position's start/end date or the assignation's effective date.
-- Kept from Retool: user_type 'Delivery Analyst' sees the RPA / Software / Managed Teams /
-- Dedicated-LSS / SaaS account types and the 'PM' account; 'Account Manager Lead' sees
-- 'Dedicated'. `has_pcu`: a PCU in the month up to :reference_date; `employee_quality_id`: a
-- performance review in :reference_date's month.
-- Fixes:
--   * positions and assignations are paired when they overlap - Retool paired every position
--     with every assignation of the employee (with employees=all, an employee with 3 positions
--     and 4 assignations got 12 rows);
--   * the position and assignation dates have their own names (position_start_date,
--     assignation_end_date...) - Retool returned two `end_date` / `person_id` columns;
--   * a PCU or review never duplicates the row (Retool joined them, one row per PCU);
--   * is_assigned: an assignation ending today is still assigned (Retool compared with now()).
WITH positions AS (
    SELECT
        er.person_id,
        pos.id AS employee_position_id,
        pos.employee_role_id,
        pos.contract_type_id,
        gct.name AS contract_type,
        pos.currency,
        pos.start_date,
        pos.effective_date,
        pos.end_date,
        pos.salary,
        CASE WHEN pos.currency = 'COP' THEN pos.cost * CAST(:factor AS numeric) ELSE pos.cost END AS employee_cost,
        pos.is_active
    FROM employee_positions pos
    JOIN employee_roles er ON er.id = pos.employee_role_id
    LEFT JOIN general_contract_types gct ON gct.id = pos.contract_type_id
    WHERE (CAST(:employee_ids AS int[]) IS NULL OR er.person_id = ANY(CAST(:employee_ids AS int[])))
      AND (:employees = 'all' OR coalesce(pos.is_active, false) = (:employees = 'active'))
      AND (CAST(:contract_type_ids AS int[]) IS NULL OR pos.contract_type_id = ANY(CAST(:contract_type_ids AS int[])))
),
-- Aggregated once and joined: pcu_responses / report_employee_quality have no index on
-- assignation_id, so per-row subqueries scanned them once per assignation.
reviews AS (
    SELECT assignation_id, max(id) AS employee_quality_id
    FROM report_employee_quality
    WHERE date_trunc('month', date) = date_trunc('month', CAST(:reference_date AS date))
    GROUP BY assignation_id
),
pcus AS (
    SELECT DISTINCT assignation_id
    FROM pcu_responses
    WHERE report_date BETWEEN CAST(:reference_date AS date) - INTERVAL '1 month' AND CAST(:reference_date AS date)
),
assignations AS (
    SELECT
        er.person_id,
        oa.id AS assignation_id,
        eop.employee_role_id,
        oa.operational_profile_id,
        oa.monthly_sales_price * oa.allocation AS sales_price,
        (oa.end_date IS NULL OR oa.end_date >= current_date) AS is_assigned,
        oa.is_billable,
        oa.allocation,
        oa.account_id,
        ca.name AS account,
        ca.billing_cycle,
        oa.effective_date,
        oa.end_date,
        oa.cost_center_id,
        gcc.name AS cost_center,
        gr.name AS role,
        gs.name AS seniority,
        rv.employee_quality_id,
        pcu.assignation_id IS NOT NULL AS has_pcu
    FROM operation_assignations oa
    JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
    JOIN employee_roles er ON er.id = eop.employee_role_id
    JOIN company_accounts ca ON ca.id = oa.account_id
    LEFT JOIN general_account_types gat ON gat.id = ca.account_type_id
    LEFT JOIN general_cost_centers gcc ON gcc.id = oa.cost_center_id
    LEFT JOIN general_roles gr ON gr.id = er.role_id
    LEFT JOIN general_seniorities gs ON gs.id = er.seniority_id
    LEFT JOIN reviews rv ON rv.assignation_id = oa.id
    LEFT JOIN pcus pcu ON pcu.assignation_id = oa.id
    WHERE (CAST(:account_ids AS int[]) IS NULL OR oa.account_id = ANY(CAST(:account_ids AS int[])))
      AND (CAST(:account_type_ids AS int[]) IS NULL OR ca.account_type_id = ANY(CAST(:account_type_ids AS int[])))
      AND (CAST(:manager_ids AS int[]) IS NULL OR ca.manager_id = ANY(CAST(:manager_ids AS int[])))
      AND (CAST(:cost_center_ids AS int[]) IS NULL OR oa.cost_center_id = ANY(CAST(:cost_center_ids AS int[])))
      AND (CAST(:role_ids AS int[]) IS NULL OR er.role_id = ANY(CAST(:role_ids AS int[])))
      AND CASE CAST(:user_type AS text)
          WHEN 'Delivery Analyst' THEN gat.name IN ('RPA', 'Software', 'Managed Teams', 'Dedicated-LSS', 'SaaS') OR ca.name = 'PM'
          WHEN 'Account Manager Lead' THEN gat.name = 'Dedicated'
          ELSE true
      END
)
SELECT
    ep.id AS person_id,
    ep.first_name,
    ep.last_name,
    concat_ws(' ', ep.first_name, ep.last_name) AS fullname,
    gdt.name AS id_type,
    ep.identification,
    ep.corporate_email,
    ep.address,
    (SELECT string_agg(t.name, ', ' ORDER BY t.name)
     FROM employee_technologies et JOIN technologies t ON t.id = et.technology_id
     WHERE et.person_id = ep.id) AS tech_stack,
    (SELECT string_agg(t.name, ', ' ORDER BY t.name)
     FROM employee_technologies et JOIN technologies t ON t.id = et.technology_id
     WHERE et.person_id = ep.id AND et.is_principal) AS main_tech,
    (SELECT string_agg(gl.name, ', ' ORDER BY gl.name)
     FROM employee_languages el JOIN general_languages gl ON gl.id = el.language_id
     WHERE el.person_id = ep.id) AS language_stack,
    p.employee_position_id,
    p.employee_role_id AS position_employee_role_id,
    p.contract_type_id,
    p.contract_type,
    p.currency,
    p.start_date AS position_start_date,
    p.end_date AS position_end_date,
    p.salary,
    p.employee_cost::float AS employee_cost,
    p.is_active,
    a.assignation_id,
    a.employee_role_id AS assignation_employee_role_id,
    a.account_id,
    a.account,
    a.billing_cycle,
    a.sales_price::float AS sales_price,
    a.is_assigned,
    a.is_billable,
    a.allocation,
    a.effective_date AS assignation_effective_date,
    a.end_date AS assignation_end_date,
    a.cost_center_id,
    a.cost_center,
    a.role,
    a.seniority,
    a.employee_quality_id,
    a.has_pcu
FROM positions p
JOIN assignations a
    ON a.person_id = p.person_id
   AND p.effective_date <= coalesce(a.end_date, 'infinity'::date)
   AND a.effective_date <= coalesce(p.end_date, 'infinity'::date)
JOIN employee_persons ep ON ep.id = p.person_id
LEFT JOIN general_document_types gdt ON gdt.id = ep.identification_type_id
WHERE (:employees = 'all' OR (a.end_date IS NULL) = (:employees = 'active'))
  AND (CAST(:date_from AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN p.start_date
       WHEN 'end_date' THEN p.end_date ELSE a.effective_date END) >= CAST(:date_from AS date))
  AND (CAST(:date_to AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN p.start_date
       WHEN 'end_date' THEN p.end_date ELSE a.effective_date END) <= CAST(:date_to AS date))
ORDER BY fullname, ep.id, a.effective_date DESC, a.assignation_id DESC, p.employee_position_id DESC
