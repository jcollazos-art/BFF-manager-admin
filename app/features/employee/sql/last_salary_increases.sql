-- Date of each employee's latest salary increase: the newest position (by effective_date,
-- across all their roles) whose salary is higher than the position before it. An employee
-- whose salary never went up has no row. Same as the Retool query, plus `pos.id` as a
-- tiebreaker so two positions with the same effective_date always compare the same way.
WITH ordered AS (
    SELECT
        er.person_id,
        pos.effective_date,
        pos.salary,
        lag(pos.salary) OVER (PARTITION BY er.person_id ORDER BY pos.effective_date, pos.id) AS previous_salary
    FROM employee_positions pos
    JOIN employee_roles er ON er.id = pos.employee_role_id
)
SELECT DISTINCT ON (person_id)
    person_id,
    effective_date
FROM ordered
WHERE salary > previous_salary
ORDER BY person_id, effective_date DESC NULLS LAST
