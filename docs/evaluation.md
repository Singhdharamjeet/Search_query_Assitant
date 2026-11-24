# Search quality evaluation

Generated: 2026-11-23 21:03

18 labelled queries that should match a course, 3 that should match nothing. No API calls are used.

## Summary

| Method | Hit@1 | Hit@3 | MRR | No-match handled |
|---|---|---|---|---|
| Keyword-only | 83% | 89% | 0.86 | 3/3 |
| TF-IDF only | 83% | 83% | 0.83 | 2/3 |
| Full pipeline search | 94% | 100% | 0.97 | 3/3 |

Hit@1: the top result is an acceptable course. Hit@3: one appears in the top 3. MRR: mean of 1/rank of the first acceptable course. No-match handled: the method returned nothing.

## Top result per query

| Query | Keyword-only | TF-IDF only | Full pipeline search |
|---|---|---|---|
| something to get better at pivot tables | OK Excel Pivot Tables and Dashboards | OK Excel Pivot Tables and Dashboards | OK Excel Pivot Tables and Dashboards |
| pivot tabel tutorial | OK Excel Pivot Tables and Dashboards | OK Excel Pivot Tables and Dashboards | OK Excel Pivot Tables and Dashboards |
| I want to lern pyhton | MISS (none) | MISS (none) | OK Python for Beginners |
| spreadsheet help | OK Excel Fundamentals | OK Excel Fundamentals | OK Excel Fundamentals |
| intro to excel | OK Excel Fundamentals | OK Excel Fundamentals | OK Excel Fundamentals |
| show beginner sql lessons | MISS Advanced SQL and Query Optimization | OK SQL Basics | OK SQL Basics |
| advanced sql | OK Advanced SQL and Query Optimization | OK Advanced SQL and Query Optimization | OK Advanced SQL and Query Optimization |
| window functions and indexes | OK Advanced SQL and Query Optimization | OK Advanced SQL and Query Optimization | OK Advanced SQL and Query Optimization |
| how do I build dashboards in power bi | OK Power BI Essentials | OK Power BI Essentials | OK Power BI Essentials |
| make charts and reports | OK Excel Fundamentals | OK Excel Fundamentals | OK Power BI Essentials |
| clean messy data with pandas | OK Python Data Analysis with Pandas | OK Python Data Analysis with Pandas | OK Python Data Analysis with Pandas |
| learn coding | OK Python for Beginners | OK Python for Beginners | OK Python for Beginners |
| how to write better emails | OK Communication Skills at Work | MISS (none) | MISS Digital Marketing Essentials |
| plan a project timeline | OK Project Management Basics | OK Project Management Basics | OK Project Management Basics |
| predict things with ml | MISS (none) | MISS (none) | OK Machine Learning Foundations |
| what is regression | OK Machine Learning Foundations | OK Machine Learning Foundations | OK Machine Learning Foundations |
| spot phishing and protect my password | OK Cyber Security Awareness | OK Cyber Security Awareness | OK Cyber Security Awareness |
| protect company data online | OK Cyber Security Awareness | OK Cyber Security Awareness | OK Cyber Security Awareness |

## Notes

- Small hand-made test set written by the project author; it shows relative improvement, not a general accuracy claim.
- The NLP rules (typos, synonyms) were built from the same course catalog, so scores on this set are optimistic.
