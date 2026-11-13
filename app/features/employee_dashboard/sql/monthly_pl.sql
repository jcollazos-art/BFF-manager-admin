-- P&L table of the dashboard for one month (:month 'YYYY-MM'): every assignation active in
-- the month paired with each position of the employee active in the month that overlaps it,
-- with profit, margin, the suggested next sale price and the resolved manager / manager lead.
-- Filters: :month, date range, user_type + account_type_names, employees (position not ended
-- / ended).
-- Business rules kept from Retool:
--   * next sale price = sales price + the account's 'Anual Increase' governance value (a
--     percentage, "3.5%" or "3.5"), suggested one year after the last price increase of the
--     assignation (or one year after it started);
--   * manager / manager lead come from the account manager and the silo hierarchy (silo
--     manager -> parent silo manager -> grandparent silo manager), skipping the employee
--     themself; 'Dedicated' accounts go by silo.
-- Fixes:
--   * COP positions: employee_cost (and so profit and margin) uses the cost converted with the
--     COP factor, like the other dashboard lists - Retool subtracted COP costs from USD prices;
--   * catalogs are LEFT JOINs - Retool's INNER JOINs dropped an assignation whose cost center
--     had no P&L, whose account had no category, etc.;
--   * one annual-increase value per account (the newest) - an account with two rows
--     duplicated its assignations;
--   * the last increase is computed per (employee, account, assignation start) for every
--     assignation, not only for the newest one of each account;
--   * Retool's five OR'd date conditions are the single overlap test they add up to;
--   * the account's manager profile id is `account_manager_profile_id` - Retool returned two
--     `manager_id` columns.
WITH positions AS (
    SELECT
        er.person_id AS employee_id,
        pos.id AS position_id,
        CASE WHEN pos.currency = 'COP' THEN pos.cost * CAST(:factor AS numeric) ELSE pos.cost END AS employee_cost,
        pos.salary,
        pos.bonus,
        pos.effective_date,
        pos.end_date,
        pos.contract_type_id,
        pos.silo_id,
        pos.currency,
        (pos.end_date IS NULL OR pos.end_date >= current_date) AS is_active,
        ep.corporate_email,
        silo_manager.id AS silo_manager_id,
        nullif(concat_ws(' ', silo_manager.first_name, silo_manager.last_name), '') AS silo_manager_name,
        silo_manager.corporate_email AS silo_manager_email,
        silo_lead.id AS silo_lead_id,
        nullif(concat_ws(' ', silo_lead.first_name, silo_lead.last_name), '') AS silo_lead_name,
        silo_lead.corporate_email AS silo_lead_email,
        silo_grandlead.id AS silo_grandlead_id,
        nullif(concat_ws(' ', silo_grandlead.first_name, silo_grandlead.last_name), '') AS silo_grandlead_name,
        silo_grandlead.corporate_email AS silo_grandlead_email
    FROM employee_positions pos
    JOIN employee_roles er ON er.id = pos.employee_role_id
    JOIN employee_persons ep ON ep.id = er.person_id
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
    WHERE pos.deleted_at IS NULL
      AND to_char(pos.effective_date, 'YYYY-MM') <= :month
      AND (pos.end_date IS NULL OR to_char(pos.end_date, 'YYYY-MM') >= :month)
),
price_changes AS (
    SELECT
        er.person_id,
        oa.account_id,
        oa.start_date,
        oa.effective_date,
        oa.monthly_sales_price > lag(oa.monthly_sales_price) OVER w AS is_increase
    FROM operation_assignations oa
    JOIN employee_operational_profiles eop ON eop.id = oa.operational_profile_id
    JOIN employee_roles er ON er.id = eop.employee_role_id
    WHERE oa.is_billable
    WINDOW w AS (PARTITION BY er.person_id, oa.account_id, oa.start_date ORDER BY oa.effective_date, oa.id)
),
next_increase AS (
    SELECT
        person_id,
        account_id,
        start_date,
        (coalesce(max(effective_date) FILTER (WHERE is_increase), start_date) + INTERVAL '1 year')::date AS next_increase_date
    FROM price_changes
    GROUP BY person_id, account_id, start_date
),
annual_increase AS (
    SELECT DISTINCT ON (gm.account_id)
        gm.account_id,
        CASE
            WHEN gm.value ~ '^[0-9]+(\.[0-9]+)?%$' THEN replace(gm.value, '%', '')::numeric / 100
            WHEN gm.value ~ '^[0-9]+(\.[0-9]+)?$' THEN gm.value::numeric / 100
        END AS increase
    FROM governance_models gm
    JOIN general_governance_concepts ggc ON ggc.id = gm.concept_id AND ggc.name = 'Anual Increase'
    WHERE gm.value ~ '^[0-9]+(\.[0-9]+)?%?$'
    ORDER BY gm.account_id, gm.updated_at DESC NULLS LAST, gm.id DESC
),
assignations AS (
    SELECT
        oa.id AS assignation_id,
        oa.account_id,
        ca.name AS account,
        ca.account_type_id,
        gat.name AS account_type,
        ca.billing_cycle,
        ca.manager_id AS account_manager_profile_id,
        account_manager.id AS account_manager_id,
        nullif(concat_ws(' ', account_manager.first_name, account_manager.last_name), '') AS account_manager_name,
        account_manager.corporate_email AS account_manager_email,
        oa.monthly_sales_price * oa.allocation AS sales_price,
        er.id AS employee_role_id,
        ep.id AS employee_id,
        concat_ws(' ', ep.first_name, ep.last_name) AS fullname,
        ep.personal_email,
        ep.corporate_email AS email,
        ep.phone_number,
        ep.photo_url,
        ep.address,
        ep.identification,
        ep.birth_date,
        gc.name AS city,
        gco.name AS country,
        gna.name AS nationality,
        gdt.name AS identification_type,
        gs.name AS seniority,
        gr.name AS role,
        oa.is_billable,
        oa.cost_center_id,
        gcc.name AS cost_center,
        gpal.name AS p_l_category,
        gsi.name AS silo_name,
        oa.allocation,
        oa.start_date,
        oa.effective_date,
        oa.end_date,
        oa.monthly_sales_price,
        ni.next_increase_date
    FROM employee_persons ep
    JOIN employee_roles er ON er.person_id = ep.id
    JOIN employee_operational_profiles eop ON eop.employee_role_id = er.id
    JOIN operation_assignations oa ON oa.operational_profile_id = eop.id
    JOIN company_accounts ca ON ca.id = oa.account_id
    LEFT JOIN general_roles gr ON gr.id = er.role_id
    LEFT JOIN general_seniorities gs ON gs.id = er.seniority_id
    LEFT JOIN general_account_types gat ON gat.id = ca.account_type_id
    LEFT JOIN general_account_categories gac ON gac.id = ca.account_category_id
    LEFT JOIN general_cost_centers gcc ON gcc.id = oa.cost_center_id
    LEFT JOIN general_profit_and_loss gpal ON gpal.id = gcc.profit_loss_id
    LEFT JOIN general_silos gsi ON gsi.id = oa.silo_id
    LEFT JOIN general_cities gc ON gc.id = ep.city_id
    LEFT JOIN general_countries gco ON gco.id = gc.country_id
    LEFT JOIN general_countries gna ON gna.id = ep.nationality_id
    LEFT JOIN general_document_types gdt ON gdt.id = ep.identification_type_id
    -- company_accounts.manager_id is an operational profile id
    LEFT JOIN employee_operational_profiles eop_am ON eop_am.id = ca.manager_id
    LEFT JOIN employee_roles er_am ON er_am.id = eop_am.employee_role_id
    LEFT JOIN employee_persons account_manager ON account_manager.id = er_am.person_id
    LEFT JOIN next_increase ni
        ON ni.person_id = ep.id AND ni.account_id = oa.account_id AND ni.start_date = oa.start_date
    WHERE to_char(oa.effective_date, 'YYYY-MM') <= :month
      AND (oa.end_date IS NULL OR to_char(oa.end_date, 'YYYY-MM') >= :month)
      AND (CAST(:date_from AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) >= CAST(:date_from AS date))
      AND (CAST(:date_to AS date) IS NULL OR (CASE CAST(:date_field AS text) WHEN 'start_date' THEN oa.start_date
           WHEN 'end_date' THEN oa.end_date ELSE oa.effective_date END) <= CAST(:date_to AS date))
      AND (CAST(:user_type AS text) IS NULL
           OR CAST(:user_type AS text) NOT IN ('Delivery Analyst', 'Account Manager Lead')
           OR gat.name = ANY(CAST(:account_type_names AS text[])))
      AND (CAST(:user_type AS text) IS DISTINCT FROM 'Account Manager Lead'
           OR gat.name IS DISTINCT FROM 'Augmented Services'
           OR gac.name IN ('Account', 'Project'))
)
SELECT
    a.*,
    p.position_id,
    p.salary,
    p.bonus,
    p.employee_cost::float AS employee_cost,
    p.currency,
    p.contract_type_id,
    p.silo_id,
    p.is_active,
    p.end_date AS position_end_date,
    a.next_increase_date AS next_sale_price_date,
    a.sales_price * (1 + coalesce(ai.increase, 0)) AS next_sale_price,
    CASE
        WHEN ai.increase IS NOT NULL THEN round(ai.increase * 100, 1) || '% annual increase'
        ELSE 'Without info'
    END AS next_sale_price_caption,
    (a.sales_price - p.employee_cost * a.allocation)::float AS profit,
    CASE
        WHEN a.sales_price > 0 THEN ((a.sales_price - p.employee_cost * a.allocation) / a.sales_price)::float
        ELSE 0
    END AS margin,
    CASE
        WHEN a.account = 'Dedicated' AND p.silo_manager_email <> p.corporate_email THEN p.silo_manager_name
        WHEN a.account_manager_email <> p.corporate_email THEN a.account_manager_name
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_name
        ELSE p.silo_lead_name
    END AS manager,
    CASE
        WHEN a.account = 'Dedicated' AND p.silo_manager_email <> p.corporate_email THEN p.silo_manager_email
        WHEN a.account_manager_email <> p.corporate_email THEN a.account_manager_email
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_email
        ELSE p.silo_lead_email
    END AS manager_email,
    CASE
        WHEN a.account = 'Dedicated' AND p.silo_manager_email <> p.corporate_email THEN p.silo_manager_id
        WHEN a.account_manager_email <> p.corporate_email THEN a.account_manager_id
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_id
        ELSE p.silo_lead_id
    END AS manager_id,
    CASE
        WHEN a.account = 'Dedicated' AND p.silo_manager_email = p.corporate_email THEN p.silo_grandlead_name
        WHEN a.account = 'Dedicated' AND p.silo_lead_email <> p.corporate_email THEN p.silo_lead_name
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_name
        WHEN p.silo_lead_email <> p.corporate_email THEN p.silo_lead_name
        ELSE p.silo_grandlead_name
    END AS manager_lead,
    CASE
        WHEN a.account = 'Dedicated' AND p.silo_manager_email = p.corporate_email THEN p.silo_grandlead_email
        WHEN a.account = 'Dedicated' AND p.silo_lead_email <> p.corporate_email THEN p.silo_lead_email
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_email
        WHEN p.silo_lead_email <> p.corporate_email THEN p.silo_lead_email
        ELSE p.silo_grandlead_email
    END AS manager_lead_email,
    CASE
        WHEN a.account = 'Dedicated' AND p.silo_manager_email = p.corporate_email THEN p.silo_grandlead_id
        WHEN a.account = 'Dedicated' AND p.silo_lead_email <> p.corporate_email THEN p.silo_lead_id
        WHEN p.silo_manager_email <> p.corporate_email THEN p.silo_manager_id
        WHEN p.silo_lead_email <> p.corporate_email THEN p.silo_lead_id
        ELSE p.silo_grandlead_id
    END AS manager_lead_id
FROM assignations a
JOIN positions p
    ON p.employee_id = a.employee_id
   AND p.effective_date <= coalesce(a.end_date, 'infinity'::date)
   AND a.effective_date <= coalesce(p.end_date, 'infinity'::date)
LEFT JOIN annual_increase ai ON ai.account_id = a.account_id
WHERE :employees = 'all' OR p.is_active = (:employees = 'active')
ORDER BY a.account_id, a.fullname, a.assignation_id, p.position_id
