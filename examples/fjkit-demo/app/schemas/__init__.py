"""Wire contracts, one module per resource.

A response model is what a route promises: FastAPI infers `response_model` from
the handler's return annotation and `@render` spreads that same model into the
template context, so this layer feeds both representations from one declaration.

Nothing here mirrors a stored row. The demo's rows live in `app/services`.
"""
