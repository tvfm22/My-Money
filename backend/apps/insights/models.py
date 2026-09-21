"""The insights app is stateless.

Insights are computed from recorded data on every request, never stored or
generated. This is deliberate: the product spec requires that insights reflect
only what the user actually recorded, and a stored insight could outlive the
data that justified it.
"""
