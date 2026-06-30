"""
option_filename_parser.py — Reusable option filename parser.

Exports:
    parse_option_filename(filename: str) -> dict

This module has no dependencies beyond the standard library and no I/O side
effects.  Phase 2+ code can import and reuse parse_option_filename directly.
"""

# Known underliers, sorted longest-first so that "BANKNIFTY" is tried before
# "NIFTY", preventing a false prefix match.
KNOWN_UNDERLIERS = ("MIDCPNIFTY", "BANKNIFTY", "FINNIFTY", "NIFTY")


def parse_option_filename(filename: str) -> dict:
    """Parse an option CSV filename into structured metadata.

    Parameters
    ----------
    filename : str
        The bare filename including the .csv extension,
        e.g. "NIFTY22110314550PE.csv".

    Returns
    -------
    dict with keys:
        filename         – original filename as passed in.
        underlier        – str or None on failure.
        expiry_date      – str "YYYY-MM-DD" or None on failure.
        strike           – int | float or None on failure.
        option_type      – "CE" | "PE" or None on failure.
        instrument_name  – filename without .csv, or None on failure.
        parse_status     – "OK" or "FAILED".
        failure_reason   – None on success, descriptive string on failure.
    """
    result = {
        "filename": filename,
        "underlier": None,
        "expiry_date": None,
        "strike": None,
        "option_type": None,
        "instrument_name": None,
        "parse_status": "FAILED",
        "failure_reason": None,
    }

    # ---- Strip .csv extension ---------------------------------------------
    if not filename.endswith(".csv"):
        result["failure_reason"] = "Filename does not end with .csv"
        return result

    stem = filename[:-4]  # remove ".csv"
    if not stem:
        result["failure_reason"] = "Empty filename after stripping .csv"
        return result

    # ---- Extract option_type (last 2 chars) -------------------------------
    option_type = stem[-2:]
    if option_type not in ("CE", "PE"):
        result["failure_reason"] = (
            f"Last 2 characters '{option_type}' are not CE or PE"
        )
        return result

    body = stem[:-2]  # everything before CE/PE

    # ---- Match underlier (longest prefix first) ---------------------------
    underlier = None
    for candidate in KNOWN_UNDERLIERS:
        if body.startswith(candidate):
            underlier = candidate
            break

    if underlier is None:
        result["failure_reason"] = (
            f"No known underlier prefix matched in '{body}'"
        )
        return result

    remainder = body[len(underlier):]  # should be YYMMDD + strike

    # ---- Extract 6-digit expiry block -------------------------------------
    if len(remainder) < 6:
        result["failure_reason"] = (
            f"Fewer than 6 characters remaining for expiry+strike: '{remainder}'"
        )
        return result

    expiry_block = remainder[:6]
    if not expiry_block.isdigit():
        result["failure_reason"] = (
            f"Expiry block '{expiry_block}' is not 6 digits"
        )
        return result

    yy = int(expiry_block[0:2])
    mm = int(expiry_block[2:4])
    dd = int(expiry_block[4:6])

    # Basic calendar sanity check
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        result["failure_reason"] = (
            f"Invalid date components in expiry block '{expiry_block}': "
            f"month={mm}, day={dd}"
        )
        return result

    expiry_date = f"20{yy:02d}-{mm:02d}-{dd:02d}"

    # ---- Extract strike ---------------------------------------------------
    strike_str = remainder[6:]
    if not strike_str:
        result["failure_reason"] = "No strike value found after expiry block"
        return result

    # Try integer first, then float.
    try:
        if "." in strike_str:
            strike = float(strike_str)
        else:
            strike = int(strike_str)
    except ValueError:
        result["failure_reason"] = (
            f"Strike '{strike_str}' is not a valid number"
        )
        return result

    # ---- Success ----------------------------------------------------------
    result["underlier"] = underlier
    result["expiry_date"] = expiry_date
    result["strike"] = strike
    result["option_type"] = option_type
    result["instrument_name"] = stem
    result["parse_status"] = "OK"
    result["failure_reason"] = None
    return result
