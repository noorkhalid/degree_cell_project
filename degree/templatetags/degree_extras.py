from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, 0)

@register.filter
def cnic_format(value):
    """Display a stored 13-digit CNIC as 00000-0000000-0."""
    value = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(value) == 13:
        return f'{value[:5]}-{value[5:12]}-{value[12]}'
    return value


@register.filter
def vc_file_no_display(value):
    """Display VC file numbers with three digits, e.g. 001/2026."""
    text = str(value or '').strip()
    if '/' not in text:
        return text
    number, year = text.split('/', 1)
    try:
        return f'{int(number):03d}/{year}'
    except (TypeError, ValueError):
        return text

@register.filter
def mobile_format(value):
    """Display a stored 11-digit mobile number as 0300-0000000."""
    value = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(value) == 11:
        return f'{value[:4]}-{value[4:]}'
    return value
