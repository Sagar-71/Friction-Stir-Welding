# Extended model setup notes

Companion to the README. Everything here is traceable to
`docs/fluent-setup-report.xml` or to the case and data files under
`simulation/fluent/`, and can be regenerated with
`python scripts/extract_results.py`.

## 1. Governing equations

The plasticised aluminium is solved as a steady, incompressible, laminar flow
with heat transfer.

Continuity:

```
div(rho * u) = 0
```

Momentum:

```
div(rho * u * u) = -grad(p) + div(eta * (grad(u) + grad(u)^T))
```

Energy, with the viscous dissipation term retained:

```
div(rho * Cp * T * u) = div(k * grad(T)) + Phi
```

where the dissipation function `Phi = eta * gammadot^2` is the sole heat
source in the domain. No frictional or plastic-work source term is prescribed
anywhere, so the total heat generation is an output of the solve.

## 2. Constitutive law

Fluent's non-Newtonian power law with the shear rate and temperature dependent
option:

```
eta = k * gammadot^(n - 1) * exp(alpha / T)
```

| Symbol | Meaning | Value |
| --- | --- | --- |
| k | consistency index | 6.88173e7 |
| n | power-law index | 0.0421 |
| alpha | activation energy over gas constant | 1380 K |
| T_alpha | reference temperature | 298 K |
| eta_min | lower viscosity clip | 1.0e3 Pa.s |
| eta_max | upper viscosity clip | 1.0e6 Pa.s |

With `n = 0.0421` the exponent on shear rate is roughly `-0.958`, so viscosity
falls almost inversely with shear rate. Deformation therefore localises very
sharply: material a few millimetres from the pin is effectively rigid while
material at the pin surface flows freely.

In the converged solution the viscosity spans 1.86e3 to 1.00e6 Pa.s. The upper
clip is active over most of the plate, which is intended, since it is what
represents the un-stirred base metal as a solid. The lower clip is never
reached, so the softest material in the stir zone is resolved by the law
itself and not by the clip.

## 3. Temperature-dependent properties

Both specific heat and thermal conductivity are third-order polynomials in
temperature, which matters over the 300 K to 591 K range the solution spans.

```
Cp(T) = 929 - 0.627 T + 1.48e-3 T^2 - 4.33e-8 T^3      [J/(kg K)]
k(T)  = 25.2 + 0.398 T + 7.36e-6 T^2 - 2.52e-7 T^3     [W/(m K)]
```

Density is held constant at 2700 kg/m3. Thermal expansion is neglected, which
is consistent with the incompressible formulation and removes any buoyancy
contribution, negligible here against the shear-driven flow.

## 4. Mesh

| Quantity | Value |
| --- | --- |
| Cells | 133,592 |
| Faces | 274,816 |
| Nodes | 26,167 |

The node to cell ratio is characteristic of an unstructured tetrahedral fill.
Refinement is concentrated around the tool: the `fswtool` wall alone carries
roughly 4,700 faces out of 274,816, against a wall area that is well under one
percent of the domain.

## 5. Named zones

| Zone | Type | Role |
| --- | --- | --- |
| `solid` | fluid cell zone | the plate, despite the name |
| `velocityinlet` | velocity inlet | leading edge, feeds material toward the tool |
| `pressureoutlet` | pressure outlet | trailing edge |
| `fswtool` | wall | tool shoulder and pin surface |
| `topface` | wall | plate top surface outside the shoulder |
| `buttomface` | wall | plate underside, backing anvil contact |
| `wall-solid` | wall | remaining side faces |
| `interior-solid` | interior | internal faces |

The zone names `solid` and `buttomface` are as they were created in the
original session and are kept unchanged so that the shipped case file and this
documentation agree.

## 6. Derived quantities and how they were obtained

All four converged loads are read from the report files in
`results/monitors/`, taken at iteration 352.

| Quantity | Derivation | Value |
| --- | --- | --- |
| Rotation speed | 74.351 rad/s x 60 / (2 pi) | 710.0 rpm |
| Traverse speed | 0.00133 m/s x 60000 | 79.8 mm/min |
| Weld pitch | 710.0 / 79.8 | 8.90 rev/mm |
| Shoulder edge speed | 74.351 x 0.012 m | 0.892 m/s |
| Spindle power | 37.7331 N.m x 74.351 rad/s | 2805.5 W |
| Heat input per length | 2805.5 W / 0.00133 m/s | 2.109 kJ/mm |
| Peak T over solidus | 590.96 K / 855 K | 0.691 |
| Peak T over liquidus | 590.96 K / 925 K | 0.639 |

AA6061 melting range taken as 582 C solidus to 652 C liquidus.

## 7. Convergence

The run was stopped at iteration 352 with a scaled continuity residual of
4.97e-05. Judging convergence on residuals alone would be weak for a problem
with this viscosity range, so the tool loads were monitored directly and the
solve was taken past the point where all four flattened.

Torque and thrust are flat from roughly iteration 260. The traverse and lateral
forces are slower: both pass through sign reversals near iterations 140 and
200, which correspond to the recirculating wake behind the pin reorganising as
the thermal field develops. The lateral force is the last to settle and is the
one to watch if the case is rerun at a different operating point.

## 8. Known issues in the shipped project

The Workbench project contains Fluent abnormal-exit entries in its error logs
dated after the successful solve. These come from closing the Fluent session,
not from the solve itself: the converged data file
`FFF-1-00352.dat.h5` reads cleanly and reproduces every number in this
document. If Workbench refuses to resolve the project on your machine, load
`simulation/mesh/FFF.msh` into a fresh Fluid Flow (Fluent) system and read the
shipped case file, which is self-contained.
