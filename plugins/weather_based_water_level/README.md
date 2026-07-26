# Weather-based Water Level

Tested with Python 3.8+.

The plug-in calculates an OSPy water-level adjustment every hour. Version 1.1.0 offers three selectable calculation methods while retaining the original multi-day method as the default for existing installations.

## Calculation methods

### Multi-day weather balance

This is the original plug-in calculation. It combines the selected history, today and forecast days. The configured reference water at 100% (default 4 mm/day) is adjusted by mean temperature, wind and relative humidity, then total rainfall is subtracted.

OSPy weather humidity uses the normalized range `0..1`. Version 1.1.0 correctly converts it to `0..100%` before applying the humidity factor.

### Zimmerman

The Zimmerman calculation uses yesterday's mean temperature and humidity plus rainfall from yesterday and today:

```text
temperature factor = (mean °C - reference °C) × 7.2
humidity factor    = reference RH% - mean RH%
rain factor        = (yesterday rain + today rain) × -7.874
adjustment         = 100 + temperature factor + humidity factor + rain factor
```

The defaults correspond to the classic 70 °F / 30% reference: 21.1 °C and 30% relative humidity. The reference values can be adapted to the local climate. The calculation period is fixed, so the multi-day history and forecast controls are hidden.

### FAO-56 ETo

This method reads `weather.get_eto()` from OSPy for 1–7 completed historical days. OSPy uses provider-supplied ETo where available and otherwise calculates FAO-56 reference evapotranspiration from weather observations.

```text
ETc            = ETo × crop coefficient
effective rain = (historical rain + today rain) × effective-rain percentage
net need       = max(0, sum(ETc) - effective rain)
gross need     = net need / irrigation efficiency
adjustment     = gross need / (reference mm/day × valid days) × 100
```

The crop coefficient describes the vegetation, irrigation efficiency accounts for delivery losses, and effective rainfall accounts for rain not retained in the root zone. Forecast days are not used.

## Common behavior

- The minimum and maximum percentage limits apply to every method.
- Freeze protection is independent of the calculation method.
- The footer can show the active method and current adjustment.
- The details page shows method-specific inputs, factors and results.
- Changing the method removes the previous method's adjustment immediately and triggers recalculation.
- If the selected method has never produced a usable result, missing data gives a neutral 100% contribution.
- A temporary data failure after a successful calculation retains only the last successful result from the same method and marks it as stale.

The plug-in declares network and system permissions, uses the shared OSPy worker lifecycle, removes its callback, footer and adjustment during shutdown, and reports its latest calculation through the Diagnostics health interface.
