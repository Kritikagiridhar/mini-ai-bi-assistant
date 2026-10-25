"""Business definitions and supported intent constants."""

# Business definitions
BUSINESS_REVENUE_DEFINITION = (
    "Revenue = Quantity * Unit_price - Discount_amount, "
    "counting only valid records with Status = 'Completed'. "
    "Discount_amount is treated as a total discount for the line."
)

DEFAULT_YEAR = "2026"

VALID_MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

VALID_REGIONS = ["North", "South", "East", "West"]
VALID_CHANNELS = ["Online", "Retail"]
VALID_STATUSES = ["Completed", "Returned"]

# Whitelisted intents
INTENT_TOTAL_REVENUE = "total_revenue"
INTENT_TOP_PRODUCT_BY_REVENUE = "top_product_by_revenue"
INTENT_MONTHLY_REVENUE_TREND = "monthly_revenue_trend"
INTENT_TOP_REGION_BY_SALES = "top_region_by_sales"
INTENT_COMPARE_MONTHS = "compare_months"
INTENT_UNSUPPORTED = "unsupported"

WHITELISTED_INTENTS = {
    INTENT_TOTAL_REVENUE,
    INTENT_TOP_PRODUCT_BY_REVENUE,
    INTENT_MONTHLY_REVENUE_TREND,
    INTENT_TOP_REGION_BY_SALES,
    INTENT_COMPARE_MONTHS,
    INTENT_UNSUPPORTED,
}

UNSUPPORTED_GUIDANCE_MESSAGE = (
    "I can only answer specific business intelligence questions based on verified 2026 sales data. "
    "Supported question types are:\n"
    "1. Total revenue (with optional filters by product, category, region, channel, or month)\n"
    "2. Top 5 products by revenue (optional region or month filter)\n"
    "3. Monthly revenue trend with Month-over-Month (MoM) growth rates\n"
    "4. Top regions ranked by sales volume and revenue share\n"
    "5. Month comparison (e.g., compare March 2026 vs April 2026)"
)
