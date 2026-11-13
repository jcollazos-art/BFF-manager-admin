-- Headcount per month since 2020-01: employees with a position covering some day of that
-- month (started in or before it, and not ended before it). `person_ids` are those
-- employees. A month without anyone has no row.
-- Same result as the Retool query, without its CROSS JOIN LATERAL of every position into
-- every month and the to_char() string comparisons: positions are matched to the months
-- they cover by date range.
SELECT
    to_char(m.month, 'YYYY-MM') AS year_month,
    count(DISTINCT er.person_id)::int AS employees,
    array_agg(DISTINCT er.person_id) AS person_ids
FROM generate_series(DATE '2020-01-01', date_trunc('month', current_date), INTERVAL '1 month') AS m(month)
JOIN employee_positions pos
    ON date_trunc('month', pos.start_date) <= m.month
   AND (pos.end_date IS NULL OR date_trunc('month', pos.end_date) >= m.month)
JOIN employee_roles er ON er.id = pos.employee_role_id
GROUP BY m.month
ORDER BY m.month
