-- Main employees table of the dashboard: one row per employee with their newest position
-- (personal data, cost, silo and its managers, tech and language stacks) and their
-- assignations matching the filters (as a JSON array, plus totals), with the resolved
-- manager / manager lead. An employee without a matching position or assignation is left out.
-- Filters: employee_ids, employees (position is_active / not), contract_type_ids (of the
-- position), include_lss (P&L of the position's cost center), account_ids, account_type_ids,
-- cost_center_ids and role_ids (of the assignation), user_type + account_type_names, date
-- range (without date_field: only assignations not ended), only_started.
-- Business rules kept from Retool: the position is the newest (highest id) one passing the
-- filters; COP costs are converted with the COP factor; manager / manager lead as in
-- monthly_pl.sql (an employee whose only account is 'Dedicated' goes by silo); `pcu_id` /
-- `employee_quality_id` are this month's PCU (per account) and performance review.
-- Fixes:
--   * one row per employee. Retool grouped the assignations by reason and account manager and
--     then kept an arbitrary group per email (DISTINCT ON without ORDER BY), so the accounts,
--     totals and reason shown could be a subset; here every matching assignation is
--     aggregated, and reason / account manager / profile / role come from the newest one;
--   * `assignations` is a JSON array - Retool joined accounts, prices and allocations into
--     ' | ' strings and built the billable checkboxes as HTML;
--   * is_assigned: an assignation ending today is still assigned (Retool compared the date
--     with now(), so it stopped at midnight);
--   * include_lss=false hides only the 'Dedicated-LSS' P&L (Retool's `<>` dropped positions
--     without P&L too);
--   * pcu_id / employee_quality_id / is_replaced / profile_match are NULL when missing (Retool
--     returned 0 for the first two) and never duplicate the row.
WITH newest_position AS (
    SELECT DISTINCT ON (er.person_id)
        er.person_id,
        pos.id AS position_id
    FROM employee_positions pos
    JOIN employee_roles er ON er.id = pos.employee_role_id
    WHERE pos.deleted_at IS NULL
      AND (CAST(:employee_ids AS int[]) IS NULL OR er.person_id = ANY(CAST(:employee_ids AS int[])))
      AND (:employees = 'all' OR coalesce(pos.is_active, false) = (:employees = 'active'))
      AND (CAST(:contract_type_ids AS int[]) IS NULL OR pos.contract_type_id = ANY(CAST(:contract_type_ids AS int[])))
    ORDER BY er.person_id, pos.id DESC
),
positions AS (
    SELECT
        ep.id,
        ep.first_name,
        ep.last_name,
        ep.corporate_email,
        ep.personal_email,
        ep.address,
        ep.identification,
        ep.identification_type_id,
        ep.birth_date,
        ep.phone_number,
        ep.city_id,
        gc.country_id,
        pos.id AS position_id,
        gcc.name AS cost_center,
        gct.name AS contract_type,
        (CASE WHEN pos.currency = 'COP' THEN pos.cost * CAST(:factor AS numeric) ELSE pos.cost END)::float AS employee_cost,
        pos.salary,
        pos.currency,
        pos.start_date,
        pos.effective_date,
        pos.end_date,
        pos.silo_id,
        er.role_id,
        gr.name AS position_role,
        gs.name AS position_seniority,
        gpal.name AS profit_and_loss,
        gsi.name AS silo,
        silo_manager.id AS silo_manager_id,
        nullif(concat_ws(' ', silo_manager.first_name, silo_manager.last_name), '') AS silo_manager_name,
        silo_manager.corporate_email AS silo_manager_email,
        silo_lead.id AS silo_lead_id,
        nullif(concat_ws(' ', silo_lead.first_name, silo_lead.last_name), '') AS silo_lead_name,
        silo_lead.corporate_email AS silo_lead_email,
        silo_grandlead.id AS silo_grandlead_id,
        nullif(concat_ws(' ', silo_grandlead.first_name, silo_grandlead.last_name), '') AS silo_grandlead_name,
        silo_grandlead.corporate_email AS silo_grandlead_email,
        (SELECT string_agg(t.name, ', ' ORDER BY t.name)
         FROM employee_technologies et JOIN technologies t ON t.id = et.technology_id
         WHERE et.person_id = ep.id) AS tech_stack,
        (SELECT string_agg(concat_ws(' ', gl.name, gll.name), ', ' ORDER BY gl.name)
         FROM employee_languages el
         LEFT JOIN general_languages gl ON gl.id = el.language_id
         LEFT JOIN general_language_levels gll ON gll.id = el.language_level_id
         WHERE el.person_id = ep.id) AS language_stack
    FROM newest_position np
    JOIN employee_positions pos ON pos.id = np.position_id
    JOIN employee_roles er ON er.id = pos.employee_role_id
    JOIN employee_persons ep ON ep.id = er.person_id
    LEFT JOIN general_cities gc ON gc.id = ep.city_id
    LEFT JOIN general_roles gr ON gr.id = er.role_id
    LEFT JOIN general_seniorities gs ON gs.id = er.seniority_id
    LEFT JOIN general_cost_centers gcc ON gcc.id = pos.cost_center_id
    LEFT JOIN general_profit_and_loss gpal ON gpal.id = gcc.profit_loss_id
    LEFT JOIN general_contract_types gct ON gct.id = pos.contract_type_id
    LEFT JOIN general_silos gsi ON gsi.id = pos.silo_id
    LEFT JOIN general_silos gs_parent ON gs_parent.id = gsi.report_to_silo_id
    LEFT JOIN general_silos gs_grandparent ON gs_grandparent.id = gs_parent.report_to_silo_id
    -- general_silos.manager_id is an operational profile id
    LEFT JOIN employee_operational_profiles eop_m ON eop_m.id = gsi.manager_id
    LEFT JOIN employee_roles er_m ON er_m.id = eop_m.employee_role_id
    LEFT JOIN employee_persons silo_manager ON silo_manager.id = er_m.person_id
    LEFT JOIN employee_operational_profiles eop_l ON eop_l.id = gs_parent.manager_id
    LEFT JOIN employee_roles er_l ON er_l.id = eop_l.employee_role_id
    LEFT JOIN employee_persons silo_lead ON silo_lead.id = er_l.person_id
    LEFT JOIN employee_operational_profiles eop_g ON eop_g.id = gs_grandparent.manager_id
    LEFT JOIN employee_roles er_g ON er_g.id = eop_g.employee_role_id
    LEFT JOIN employee_persons silo_grandlead ON silo_grandlead.id = er_g.person_id
    WHERE CAST(:include_lss AS boolean) OR gpal.name IS DISTINCT FROM 'Dedicated-LSS'
),
-- This month's PCU per (employee, account) and performance review per employee, and the
-- resource releases per assignation: aggregated once, then joined (these tables have no index
-- on assignation_id, so per-row subqueries scanned them once per row).
pcu_this_month AS (
    SELECT er.person_id, oa.account_id, max(pcu.id) AS pcu_id
    FROM pcu_responses pcu
    JOIN operation_assignations oa ON oa.id = pcu.assignation_id
    JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
    JOIN employee_roles er ON er.id = eop.employee_role_id
    WHERE date_trunc('month', pcu.report_date) = date_trunc('month', current_date)
    GROUP BY er.person_id, oa.account_id
),
review_this_month AS (
    SELECT er.person_id, max(req.id) AS employee_quality_id
    FROM report_employee_quality req
    JOIN operation_assignations oa ON oa.id = req.assignation_id
    JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
    JOIN employee_roles er ON er.id = eop.employee_role_id
    WHERE date_trunc('month', req.date) = date_trunc('month', current_date)
    GROUP BY er.person_id
),
releases AS (
    SELECT assignation_id, bool_or(is_replaced) AS is_replaced
    FROM operation_resource_releases
    GROUP BY assignation_id
),
assignations AS (
    SELECT
        er.person_id,
        oa.id AS assignation_id,
        oa.operational_profile_id,
        oa.account_id,
        ca.name AS account,
        ca.account_category_id,
        ca.billing_cycle,
        oa.is_billable,
        trunc(oa.monthly_sales_price * oa.allocation, 2) AS sales_price,
        oa.allocation,
        oa.start_date,
        gcc.name AS cost_center,
        gpal.name AS profit_loss,
        gr.name AS reason,
        (oa.end_date IS NULL OR oa.end_date >= current_date) AS is_assigned,
        nullif(concat_ws(' ', talent.first_name, talent.last_name), '') AS talent_partner,
        nullif(concat_ws(' ', tech.first_name, tech.last_name), '') AS tech_partner,
        account_manager.id AS account_manager_id,
        nullif(concat_ws(' ', account_manager.first_name, account_manager.last_name), '') AS account_manager_name,
        account_manager.corporate_email AS account_manager_email,
        pcu.pcu_id
    FROM employee_roles er
    JOIN employee_operational_profiles eop ON eop.employee_role_id = er.id
    JOIN operation_assignations oa ON oa.operational_profile_id = eop.id
    JOIN company_accounts ca ON ca.id = oa.account_id
    LEFT JOIN general_account_types gat ON gat.id = ca.account_type_id
    LEFT JOIN general_account_categories gac ON gac.id = ca.account_category_id
    LEFT JOIN general_reasons gr ON gr.id = oa.reason_id
    LEFT JOIN general_cost_centers gcc ON gcc.id = oa.cost_center_id
    LEFT JOIN general_profit_and_loss gpal ON gpal.id = gcc.profit_loss_id
    LEFT JOIN company_talent_partners talent ON talent.id = ca.talent_partner_id
    LEFT JOIN company_tech_partners ctp ON ctp.id = ca.tech_partner_id
    LEFT JOIN employee_persons tech ON tech.id = ctp.person_id
    -- company_accounts.manager_id is an operational profile id
    LEFT JOIN employee_operational_profiles eop_am ON eop_am.id = ca.manager_id
    LEFT JOIN employee_roles er_am ON er_am.id = eop_am.employee_role_id
    LEFT JOIN employee_persons account_manager ON account_manager.id = er_am.person_id
    LEFT JOIN pcu_this_month pcu ON pcu.person_id = er.person_id AND pcu.account_id = oa.account_id
    WHERE (CAST(:account_ids AS int[]) IS NULL OR oa.account_id = ANY(CAST(:account_ids AS int[])))
      AND (CAST(:account_type_ids AS int[]) IS NULL OR ca.account_type_id = ANY(CAST(:account_type_ids AS int[])))
      AND (CAST(:cost_center_ids AS int[]) IS NULL OR oa.cost_center_id = ANY(CAST(:cost_center_ids AS int[])))
      AND (CAST(:role_ids AS int[]) IS NULL OR er.role_id = ANY(CAST(:role_ids AS int[])))
      AND (CAST(:user_type AS text) IS NULL
           OR CAST(:user_type AS text) NOT IN ('Delivery Analyst', 'Account Manager Lead')
           OR gat.name = ANY(CAST(:account_type_names AS text[])))
      AND (CAST(:user_type AS text) IS DISTINCT FROM 'Account Manager Lead'
           OR gat.name IS DISTINCT FROM 'Augmented Services'
           OR gac.name IN ('Account', 'Project'))
      AND (CAST(:date_field AS text) IS NOT NULL OR oa.end_date IS NULL OR oa.end_date >= current_date)
      AND (CAST(:date_from AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) >= CAST(:date_from AS date))
      AND (CAST(:date_to AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) <= CAST(:date_to AS date))
      AND (NOT CAST(:only_started AS boolean) OR oa.effective_date <= current_date)
),
accounts AS (
    SELECT
        a.person_id,
        max(a.assignation_id) AS assignation_id,
        json_agg(json_build_object(
            'assignation_id', a.assignation_id,
            'account_id', a.account_id,
            'account', a.account,
            'is_billable', a.is_billable,
            'is_assigned', a.is_assigned,
            'sales_price', a.sales_price,
            'allocation', a.allocation,
            'cost_center', a.cost_center,
            'profit_loss', a.profit_loss,
            'talent_partner', a.talent_partner,
            'tech_partner', a.tech_partner,
            'pcu_id', a.pcu_id
        ) ORDER BY a.assignation_id) AS assignations,
        count(*)::int AS count_assignations,
        bool_or(a.is_billable) AS is_billable,
        sum(a.sales_price)::float AS sales_prices,
        sum(a.allocation)::float AS allocations,
        max(a.start_date) AS start_date_assignation,
        max(a.pcu_id) AS pcu_id,
        count(*) = 1 AND bool_and(a.account = 'Dedicated') AS only_dedicated
    FROM assignations a
    GROUP BY a.person_id
)
SELECT
    p.id,
    concat_ws(' ', p.first_name, p.last_name) AS fullname,
    p.first_name,
    p.last_name,
    p.corporate_email,
    p.personal_email,
    p.address,
    p.identification,
    p.identification_type_id,
    p.birth_date,
    p.phone_number,
    p.city_id,
    p.country_id,
    p.position_id,
    p.cost_center,
    p.contract_type,
    p.employee_cost,
    p.salary,
    p.currency,
    p.start_date,
    p.effective_date,
    p.end_date,
    p.silo_id,
    p.silo,
    p.profit_and_loss,
    p.tech_stack,
    p.language_stack,
    p.role_id,
    p.position_role,
    p.position_seniority,
    ac.assignations,
    ac.count_assignations,
    ac.is_billable,
    ac.sales_prices,
    ac.allocations,
    ac.start_date_assignation,
    ac.pcu_id,
    rv.employee_quality_id,
    la.assignation_id,
    la.account_category_id,
    la.reason,
    la.account_manager_id,
    la.account_manager_name,
    la.account_manager_email,
    eop.id AS profile_id,
    eop.is_available,
    rel.is_replaced,
    gr.name AS role,
    gse.name AS seniority,
    (SELECT max(sm.profile_match) FROM employee_skillmatch sm WHERE sm.personal_email = p.personal_email)::float AS profile_match,
    CASE
        WHEN ac.only_dedicated AND p.silo_manager_email <> p.corporate_email THEN p.silo_manager_name
        WHEN la.account_manager_email <> p.corporate_email THEN la.account_manager_name
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_name
        ELSE p.silo_lead_name
    END AS manager,
    CASE
        WHEN ac.only_dedicated AND p.silo_manager_email <> p.corporate_email THEN p.silo_manager_email
        WHEN la.account_manager_email <> p.corporate_email THEN la.account_manager_email
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_email
        ELSE p.silo_lead_email
    END AS manager_email,
    CASE
        WHEN ac.only_dedicated AND p.silo_manager_email <> p.corporate_email THEN p.silo_manager_id
        WHEN la.account_manager_email <> p.corporate_email THEN la.account_manager_id
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_id
        ELSE p.silo_lead_id
    END AS manager_id,
    CASE
        WHEN ac.only_dedicated AND p.silo_manager_email = p.corporate_email THEN p.silo_grandlead_name
        WHEN ac.only_dedicated AND p.silo_lead_email <> p.corporate_email THEN p.silo_lead_name
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_name
        WHEN p.silo_lead_email <> p.corporate_email THEN p.silo_lead_name
        ELSE p.silo_grandlead_name
    END AS manager_lead,
    CASE
        WHEN ac.only_dedicated AND p.silo_manager_email = p.corporate_email THEN p.silo_grandlead_email
        WHEN ac.only_dedicated AND p.silo_lead_email <> p.corporate_email THEN p.silo_lead_email
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_email
        WHEN p.silo_lead_email <> p.corporate_email THEN p.silo_lead_email
        ELSE p.silo_grandlead_email
    END AS manager_lead_email,
    CASE
        WHEN ac.only_dedicated AND p.silo_manager_email = p.corporate_email THEN p.silo_grandlead_id
        WHEN ac.only_dedicated AND p.silo_lead_email <> p.corporate_email THEN p.silo_lead_id
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_id
        WHEN p.silo_lead_email <> p.corporate_email THEN p.silo_lead_id
        ELSE p.silo_grandlead_id
    END AS manager_lead_id
FROM positions p
JOIN accounts ac ON ac.person_id = p.id
JOIN assignations la ON la.assignation_id = ac.assignation_id
JOIN employee_operational_profiles eop ON eop.id = la.operational_profile_id
LEFT JOIN employee_roles er ON er.id = eop.employee_role_id
LEFT JOIN general_roles gr ON gr.id = er.role_id
LEFT JOIN general_seniorities gse ON gse.id = er.seniority_id
LEFT JOIN review_this_month rv ON rv.person_id = p.id
LEFT JOIN releases rel ON rel.assignation_id = la.assignation_id
ORDER BY fullname, p.id
