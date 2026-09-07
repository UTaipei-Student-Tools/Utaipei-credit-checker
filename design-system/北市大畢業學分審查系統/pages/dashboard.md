# Dashboard Page Overrides

> **PROJECT:** 北市大畢業學分審查系統
> **Generated:** 2026-09-02 16:55:59
> **Page Type:** Dashboard / Data View

> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** 1200px (standard)
- **Layout:** Full-width sections, centered content
- **Sections:** 1. Hero (Value Prop + Form), 2. Recent Issues/Archives, 3. Social Proof (Subscriber count), 4. About Author

### Spacing Overrides

- No overrides — use Master spacing

### Typography Overrides

- No overrides — use Master typography

### Color Overrides

- **Strategy:** Minimalist. Paper-like background. Text focus. Accent color for Subscribe.

### Component Overrides

- Avoid: Desktop-first causing mobile issues
- Avoid: Icon buttons without labels
- Avoid: Keyboard traps or illogical tab order

---

## Page-Specific Components

- No unique components for this page

---

## Recommendations

- Effects: Minimal glow (text-shadow: 0 0 10px), dark-to-light transitions, low white emission, high readability, visible focus
- Responsive: Start with mobile styles then add breakpoints
- Accessibility: Add aria-label for icon-only buttons
- Accessibility: Tab order matches visual order
- CTA Placement: Hero inline form + Sticky header form
