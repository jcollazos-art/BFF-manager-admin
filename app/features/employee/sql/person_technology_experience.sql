-- Technologies of an employee with the experience gained on each account that uses them
-- (technology_accounts). Replaces the Retool "employee_tech" query, with these fixes:
--   * no join to employee_roles: Retool repeated every technology once per role the
--     employee has;
--   * seniority and category are LEFT JOINs, so a technology missing either is still listed.
-- Kept from Retool: `exp_in_days` on an account is its longest assignation (MAX, not the
-- sum), an open assignation counts up to today, and `exp_in_year` is truncated to 1 decimal.
-- One row per (technology, account); a technology with no such account is a single row with
-- the account and experience columns null.
WITH experience AS (
    SELECT
        oa.account_id,
        ta.technology_id,
        max(ca.name) AS account,
        max(abs(coalesce(oa.end_date, current_date) - oa.start_date)) AS exp_in_days
    FROM employee_roles er
    JOIN employee_operational_profiles eop ON eop.employee_role_id = er.id
    JOIN operation_assignations oa ON oa.operational_profile_id = eop.id
    JOIN company_accounts ca ON ca.id = oa.account_id
    JOIN technology_accounts ta ON ta.account_id = oa.account_id
    WHERE er.person_id = :person_id
    GROUP BY oa.account_id, ta.technology_id
)
SELECT
    et.person_id,
    t.id AS technology_id,
    t.name AS technology,
    gtc.name AS type,
    gs.name AS seniority,
    x.exp_in_days,
    trunc(coalesce(x.exp_in_days, 0) / 365.0, 1) AS exp_in_year,
    x.account_id,
    x.account
FROM employee_technologies et
JOIN technologies t ON t.id = et.technology_id
LEFT JOIN general_technology_categories gtc ON gtc.id = t.category_id
LEFT JOIN general_seniorities gs ON gs.id = et.seniority_id
LEFT JOIN experience x ON x.technology_id = t.id
WHERE et.person_id = :person_id
ORDER BY t.name, x.exp_in_days DESC NULLS LAST, x.account_id
