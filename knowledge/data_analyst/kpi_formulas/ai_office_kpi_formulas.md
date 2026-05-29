# AI Office KPI formulas

## Source status

These formulas cover AI Office pilot operations and the business case. Company
product metrics such as retention, LTV, CAC and ROI must be replaced or
confirmed by the official analytics team before production use.

## Task economics

### Cost per task

```text
cost_per_task = input_tokens / 1_000_000 * input_price
              + output_tokens / 1_000_000 * output_price
```

### Monthly agent cost

```text
monthly_agent_cost = number_of_tasks * average_cost_per_task
```

### Escalated support cost

```text
support_ticket_cost = l1_input_cost + l1_output_cost
                    + l2_input_cost + l2_output_cost
```

Only include L2 cost when escalation happens.

## Quality metrics

### Route accuracy

```text
route_accuracy = correctly_routed_tasks / total_routed_tasks
```

### Human correction rate

```text
human_correction_rate = tasks_requiring_material_human_fix / completed_tasks
```

### Escalation rate

```text
escalation_rate = escalated_support_tasks / total_support_tasks
```

### Needs-review rate

```text
needs_review_rate = needs_review_outputs / total_outputs
```

## Missing official KPI definitions

Do not calculate the following from generic internet formulas unless the company
approves definitions:

- retention;
- LTV;
- CAC;
- ROI;
- churn;
- active user definitions;
- revenue recognition metrics.

If a user asks for one of these and the formula is not loaded, answer that the
official formula is missing and ask PMO for a verified source.

