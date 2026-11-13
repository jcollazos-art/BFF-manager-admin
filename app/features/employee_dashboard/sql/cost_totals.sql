-- Totals of the whole cost history (cost_employee_history, every cycle): real cost and cost,
-- summed and averaged per history row. No filters, as in Retool.
-- Fix: each history row counts once. Retool joined it to every role of the employee, so the
-- cost of an employee with two roles was summed twice (and one whose role had no role or
-- seniority was left out).
SELECT
    sum(coalesce(ceh.real_cost, 0))::float AS real_cost,
    avg(coalesce(ceh.real_cost, 0))::float AS avg_real_cost,
    sum(coalesce(ceh.cost, 0))::float AS cost,
    avg(coalesce(ceh.cost, 0))::float AS avg_cost
FROM cost_employee_history ceh
JOIN employee_persons ep ON ep.id = ceh.person_id
