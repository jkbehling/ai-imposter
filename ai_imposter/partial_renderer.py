from django.template.loader import get_template

def render_partial(template_name, partial_name, context):
    """
    Search for the partial block within the template and render it with the given context.
    """
    template = get_template(template_name)
    template.render()
    partial = template.template.nodelist[0].blocks.get(partial_name)
    if not partial:
        raise ValueError(f"Partial '{partial_name}' not found in template '{template_name}'")
    return partial.render(context)
