# Design reference

This dashboard implements the **Analytics & reporting** screen from the Claude
Design project **"VisionEnforce Operations Dashboard"**.

- Source file: `Analytics & reporting.dc.html`
- Project: https://claude.ai/design/p/923189ee-ac82-44ea-ae83-d5d4a79ab6e4

The `.dc.html` is a Claude Design preview format (custom `<x-dc>` / `sc-for`
templating). This React app reproduces its layout and theme in plain JS and
wires each panel to live backend endpoints:

| Panel | Endpoint |
|-------|----------|
| Violation trend | `GET /api/analytics/weekly` (`by_day`) |
| Decision split donut | `GET /api/analytics/weekly` (`total`, `auto_challan`) |
| Zone × hour heatmap | `GET /api/analytics/zone-hour` |
| Camera false-positive table | `GET /api/analytics/camera-report` |
| Search bar | `GET /api/challans` |
