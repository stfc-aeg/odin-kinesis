"""Stage encoder conversion specifications.

Map stage model names to encoder scale factors to convert between physical units
and device encoder counts.
"""

STAGE_SPECS = {
    'MTS25-Z8': {
        'description': 'Thorlabs MTS25-Z8 encoder linear stage',
        'encoder_counts_per_mm': 34554.96,
        'encoder_counts_per_mm_s': 772981.3692,
        'encoder_counts_per_mm_s2': 263.8443072,
    },
    'MTS50-Z8': {
        'description': 'Thorlabs MTS50-Z8 encoder linear stage',
        'encoder_counts_per_mm': 34554.96,
        'encoder_counts_per_mm_s': 772981.3692,
        'encoder_counts_per_mm_s2': 263.8443072,
    },
    'PD1VM': {  # Placeholder as example, piezo handling is totally different
        'description': 'Thorlabs PD1VM piezo stage',
        'encoder_counts_per_mm': 1.0,
        'encoder_counts_per_mm_s': 1.0,
        'encoder_counts_per_mm_s2': 1.0,
    },
}

def get_stage_spec(stage_type):
    """Get encoder specifications for a given stage type.
    
    :param stage_type: Stage model string (e.g., 'MTS50-Z8')
    :return: Dict with encoder conversion factors or default if unknown
    :raises KeyError: If stage type is not recognized
    """
    if stage_type not in STAGE_SPECS:
        raise KeyError(f"Unknown stage type: {stage_type}")
    return STAGE_SPECS[stage_type]

def val_to_enc(stage_type, val, val_type):
    """Convert physical value to encoder counts.
    
    :param stage_type: Stage model string
    :param val: Physical value to convert
    :param val_type: Type string ('POS', 'VEL', or 'ACC')
    :return: Encoder count as integer
    """
    spec = get_stage_spec(stage_type)
    
    match val_type:
        case 'POS':
            return int(val * spec['encoder_counts_per_mm'])
        case 'VEL':
            return int(val * spec['encoder_counts_per_mm_s'])
        case 'ACC':
            return int(val * spec['encoder_counts_per_mm_s2'])
        case _:
            raise ValueError(f"Unknown value type: {val_type}")

def enc_to_val(stage_type, enc, val_type):
    """Convert encoder counts to physical value.
    
    :param stage_type: Stage model string
    :param enc: Encoder count value
    :param val_type: Type string ('POS', 'VEL', or 'ACC')
    :return: Physical value with appropriate precision
    """
    spec = get_stage_spec(stage_type)
    
    match val_type:
        case 'POS':
            return round(enc / spec['encoder_counts_per_mm'], 4)
        case 'VEL':
            return round(enc / spec['encoder_counts_per_mm_s'], 4)
        case 'ACC':
            return round(enc / spec['encoder_counts_per_mm_s2'], 4)
        case _:
            raise ValueError(f"Unknown value type: {val_type}")
