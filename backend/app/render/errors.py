class TemplateRenderError(ValueError):
    """The uploaded template cannot be rendered (bad syntax, blocked construct). Reported as HTTP 422."""
