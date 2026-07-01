from django import template

register = template.Library()


@register.filter
def get(d, key):
    """Dict lookup: {{ my_dict|get:key }}"""
    return d.get(key, '')
