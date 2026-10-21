"""Direct-beam transmission colour under explicitly fixed optical assumptions."""

import math

import colour
import miepython
import numpy as np

from engine import spectrum


SHAPE = colour.SpectralShape(360, 830, 1)
CMFS = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(SHAPE)
ILLUMINANT = colour.SDS_ILLUMINANTS["D65"].copy().align(SHAPE)


def transmission_colour(diameter_nm, n_real, k, n_env=1.0, optical_depth=.25):
    spectrum([550], diameter_nm, n_real, k, n_env)
    if isinstance(optical_depth, bool) or not math.isfinite(optical_depth) or not 0 <= optical_depth <= 2:
        raise ValueError("Reference optical depth must be between 0 and 2.")
    wavelengths = SHAPE.wavelengths
    qext, _, _, _ = miepython.efficiencies(complex(n_real, -k), diameter_nm, wavelengths, n_env=n_env)
    qext = np.asarray(qext, dtype=float)
    if not np.all(np.isfinite(qext)) or np.any(qext < 0):
        raise ValueError("Invalid extinction efficiencies.")
    # optical_depth = column number density * geometric area of a 200 nm sphere.
    transmission = np.exp(-optical_depth * (diameter_nm / 200) ** 2 * qext)
    xyz = colour.sd_to_XYZ(colour.SpectralDistribution(dict(zip(wavelengths, transmission))),
                           cmfs=CMFS, illuminant=ILLUMINANT, method="Integration") / 100
    linear_display = colour.XYZ_to_sRGB(xyz)
    rgb = np.clip(linear_display, 0, 1)
    values = np.rint(255 * rgb).astype(int)
    return {"hex": "#" + "".join(f"{v:02x}" for v in values), "srgb": rgb.tolist(),
            "xyz": xyz.tolist(), "gamut_clipped": bool(np.any((linear_display < 0) | (linear_display > 1))),
            "relative_luminance": float(xyz[1]), "reference_optical_depth": optical_depth,
            "assumptions": "D65; CIE 1931 2 degree observer; homogeneous spheres; direct beam; dilute independent particles; no multiple scattering"}
