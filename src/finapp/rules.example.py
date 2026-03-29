"""
Rule-based transaction categorization.

Copy this file to rules.py and customize it for your own merchants.
Rules are matched case-insensitively against the transaction's merchant name.
They run before AI categorization — anything unmatched is sent to Claude (if API key is set).

Format: ("keyword", "Category")
"""

# (substring_to_match, category)
RULES = [
    # Housing
    # ("your landlord name", "Rent"),

    # Internal transfers — add your own name as it appears in bank transfer descriptions
    # This prevents transfers between your own accounts from inflating income/expense totals.
    # ("YOUR FULL NAME", "Internal Transfer"),

    # Investments
    # ("your broker name", "Investments"),

    # Groceries
    # ("edeka", "Groceries"),
    # ("rewe", "Groceries"),

    # Subscriptions
    # ("spotify", "Subscriptions"),

    # Transport
    # ("uber", "Transport"),

    # Dining
    # ("coffee", "Dining"),
    # ("restaurant", "Dining"),
]
