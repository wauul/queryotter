---
name: QueryOtter
description: Riverbench — a readable database workbench with inspectable evidence.
colors:
  ground: "#f3f6f8"
  surface: "#fcfdfe"
  surface-alt: "#eaf0f4"
  ink: "#162b38"
  muted: "#4c6472"
  border: "#cad7df"
  control-border: "#738b9a"
  accent: "#236582"
  accent-hover: "#184e68"
  on-accent: "#fcfdfe"
  selected: "#dfedf4"
  success: "#24624a"
  success-bg: "#e4f2eb"
  warning: "#7b4b12"
  warning-bg: "#fff0d9"
  danger: "#a12c3d"
  danger-bg: "#fce9ed"
  dark-ground: "#101c24"
  dark-surface: "#162630"
  dark-surface-alt: "#1c303b"
  dark-ink: "#e5edf2"
  dark-muted: "#abc1cf"
  dark-border: "#36505e"
  dark-control-border: "#6c8897"
  dark-accent: "#9ccde0"
  dark-accent-hover: "#c0e1ed"
  dark-on-accent: "#102632"
  dark-selected: "#233f4c"
  dark-success: "#a0d9bb"
  dark-success-bg: "#193d31"
  dark-warning: "#eac58e"
  dark-warning-bg: "#49351d"
  dark-danger: "#f2b0bb"
  dark-danger-bg: "#492733"
typography:
  display:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "clamp(2.5rem, 4.3vw, 4rem)"
    fontWeight: 600
    lineHeight: 1.06
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  body:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
  metadata:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "0.75rem"
  code:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.7
rounded:
  tag: "4px"
  control: "6px"
  panel: "12px"
spacing:
  micro: "4px"
  compact: "8px"
  small: "12px"
  medium: "16px"
  content: "20px"
  group: "24px"
  page: "32px"
  section: "48px"
  wide: "64px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.on-accent}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-alt}"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  tag:
    backgroundColor: "{colors.surface-alt}"
    textColor: "{colors.muted}"
    typography: "{typography.metadata}"
    rounded: "{rounded.tag}"
    padding: "4px 8px"
  tag-success:
    backgroundColor: "{colors.success-bg}"
    textColor: "{colors.success}"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
  navigation-selected:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.accent}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
---

# Design System: QueryOtter

## Overview

**Creative North Star: "Riverbench"**

Riverbench is a cool, readable measurement workbench. The preserved otter provides warmth; native controls, actual schema names and ruled evidence provide technical confidence. Comfortable prose and denser query surfaces share the same palette, fonts and interaction vocabulary.

The QueryOtter name and original artwork, geometry and colors in `web/Otter.tsx` are binding user decisions: preserve the file unchanged, including in dark mode. [PRODUCT.md](PRODUCT.md) informs explicit review, scope and action labels without prescribing every page composition. Visual ground truth is `web/style.css`, `web/studio.css` and the sampled landing, workspace, connection, documentation, theme and experiment components. Verification belongs in [redesign-verification.md](docs/redesign-verification.md).

Impeccable's direction seed was b943d43f in Operate mode. Grounded candidate 5, the river-survey measurement workbench, was selected under the user's explicit autonomous-choice brief. The build is code-led, with no approved raster comp or painted assets.

Three complete directions were considered under the user's autonomous choice brief:

| Direction | Composition and typography | Palette and character | Signature and tradeoff |
| --- | --- | --- | --- |
| **Riverbench — selected** | Open SQL specimen beside a left-aligned proposition; persistent navigation, query panes and schema column. IBM Plex Sans with Plex Mono for code and measurements. | Cool pearl, river ink and blue; deliberate navy and pale-blue dark theme; warm original otter. Small corners and ruled rows. | Question, review and evidence form meaningful task sequences. Measurement rows pair baseline, candidate and scope. Fits technical density and readable guidance. |
| Night watch | Horizontal command strip, chronological operation log and dominant native query. Sans labels and compact code. | Proposed night #0d171b, #9be6ca, #eaa76d; day #eef5f2, #153b31. Rectangular controls and timeline markers. | Keyboard-first investigation log. Strong for frequent engineers, weaker for initial connection setup and general analysts. |
| Otter atlas | Indexed chapters, connection passports and offset catalog spreads. Geometric sans headings and tabular annotations. | Proposed paper #f1eee7, blue #294360, rust #be542e; dark #20252d with #dca98c. Square chapter tabs. | Catalog index and capability legends. Strong for discovery, with extra editorial apparatus during frequent execution. |

Alternative palettes record considered options; they are not implementation tokens. Seed b943d43f selected the river survey/measurement workbench. Clock, fold and lexicon challengers informed fixed numeric slots, progressive disclosure and bounded prose; literal LED motifs, folding animation and spectral decoration were declined. Taste, Impeccable and UI UX Pro Max guidance informed the pass. 21st.dev's MIT Campsite theme toggle and table collections were references; the shipped native theme select adds no animation dependency. Self-hosted Fontsource IBM Plex fonts carry OFL licenses. No Figma, Stitch or generated image comp is claimed as a design source.

**Key Characteristics:**
- Cool paired themes with a warm, unchanged original mascot.
- Flat ruled evidence and restrained outlined panels.
- Humanist technical type with monospace for code and measurements.
- Explicit actions, labelled native controls and purposeful mobile disclosure.

## Colors

River blue supplies action and selection; pearl and navy surfaces keep evidence readable in both registers. Frontmatter records exact source values. Unprefixed tokens are light defaults; `dark-*` entries record the dark overrides of the same CSS semantic roles, not a separate component vocabulary.

### Primary
- **River Blue / Pale River Blue — accent:** actions, links, selected navigation, active tab rules, focus, progress and caret.
- **Deep River / Bright River — accent-hover:** primary-action hover.
- **Action Contrast — on-accent:** text on accent fills and text selection.
- **River Wash — selected:** selected navigation, avatars and operation surfaces.

### Secondary
- **Verification Green — success / success-bg:** positive status and added query lines.
- **Review Amber — warning / warning-bg:** clarification and warning feedback.
- **Error Rose — danger / danger-bg:** failures, destructive actions and removed query lines. Status meaning also appears in text or icons.

### Neutral
- **Pearl / Deep Navy — ground:** page canvas.
- **Clear Paper / Navy Surface — surface:** controls, work panels and dialogs.
- **Cool Wash / Raised Navy — surface-alt:** table headers, code blocks, secondary hover and editor footers.
- **River Ink / Pale Ink — ink:** primary text.
- **Slate / Pale Slate — muted:** helpers, metadata and secondary navigation.
- **Fine Rule — border:** panel edges, table rules and dividers.
- **Control Rule — control-border:** fields, secondary buttons, upload outlines and scrollbars. It remains distinct from the finer structural rule.

### Named Rules
**The Paired Register Rule.** Resolve semantic roles through the theme; do not simulate dark mode by inverting the light palette.

**The Evidence Color Rule.** Use status colors for actual status and query differences, with words or icons carrying their meaning.

## Typography

**Display Font:** IBM Plex Sans, with sans-serif fallback.

**Body Font:** IBM Plex Sans, with sans-serif fallback.
**Label/Mono Font:** IBM Plex Mono, with monospace fallback.

**Character:** Plex Sans is open and technical without sacrificing readable instructions. Plex Mono gives queries and measurements predictable alignment. The build loads Sans 400, 500 and 600 and Mono 400 through four self-hosted Latin Fontsource stylesheets with swap rendering.

### Hierarchy
- **Display:** landing proposition; the fluid frontmatter role becomes 2.75rem at 900px and 2.625rem at 680px.
- **Headline:** workspace headings; 1.625rem on small screens. Prose headings use 2.25rem, reducing to 1.875rem.
- **Title:** default section titles. Public explanatory sections use 1.75rem, reducing to 1.625rem. Panel headings use 1rem; contextual headings use 1.0625–1.125rem.
- **Body:** default text; product descriptions commonly use 0.875–0.9375rem. Prose is bounded to 68ch with 1.8 line height; landing lead copy is 42ch with 1.7 line height.
- **Label:** controls and buttons, sentence case. Helpers use 0.8125rem; metadata uses the compact frontmatter role.
- **Code:** editors and code blocks. Tables and usage rows use tabular numerals; benchmark values use Plex Mono. Mobile query editor text increases to 1rem.

### Named Rules
**The Measurement Type Rule.** Reserve monospace for queries, schema identifiers, counts and measurements; use Sans for instructions and actions.

## Layout

Spacing clusters around the observed compact, medium and group steps, with larger separation between public sections. Public containers are 1280px wide with 32px side padding; workspace content is bounded to 1352px. Documentation uses a 900px container and bounded prose.

The desktop workspace has a fixed 232px rail, a 68px top bar and a flexible query column beside 290px of schema. At 1150px schema narrows to 245px, content padding becomes 24px and four-column metrics become two columns. At 900px the rail becomes a 280px toggleable overlay, workspace fills the width and schema moves above the query as collapsed progressive disclosure with Show fields / Hide fields. At 680px studio content uses 16px side padding, connection and settings grids become one column, form rows stack and dialog margins shrink. Public specimen and prose follow the same content rather than shrinking it. The experiment portfolio shares semantic tokens and has its own 640px small-screen breakpoint.

Dense tables scroll inside their own containers. Pagination keeps previous, page count and next in one labelled group while its footer wraps. Dialogs constrain height to the viewport and scroll internally. Ordinary buttons, selects and summaries have a 44px minimum height; checkbox/radio glyphs are 20px. Mobile connection fields and query editor text are 16px.

## Elevation & Depth

Most surfaces are flat: tone and fine rules separate work areas. Soft elevation is reserved for dialogs and mobile navigation overlays, using the shared shadow token. The dim dialog backdrop is `#071923a6`. Navigation, headers, dialogs and skip navigation use layers 10, 20, 50 and 60 respectively.

### Shadow Vocabulary
- **Light overlay:** `0 20px 60px #162b3826`.
- **Dark overlay:** `0 20px 60px #06101780`.

### Named Rules
**The Working Surface Rule.** Keep query, schema and evidence surfaces flat; use overlay elevation when a layer temporarily covers the workspace.

## Shapes

Controls have gently curved corners; tags are tighter and panels are broader, as recorded in frontmatter. Table rows, schema columns, candidate lists and tabs use flat ruled geometry. Selected tabs use an accent bottom rule. Dashed borders identify upload destinations. Existing avatar and indicator circles remain functional exceptions to rectangular working surfaces.

## Components

### Buttons
Compact and explicit. Primary buttons use accent and action-contrast; secondary buttons use surface, ink and the stronger control rule. Large public buttons have 48px minimum height, 12px 20px padding and 0.9375rem type. Icon actions are 44px square. Text actions use accent without a fill. Destructive buttons use danger with surface text in light mode and ground text in dark mode.

Hover changes primary fill to accent-hover and secondary fill to surface-alt. Global visible focus is a 3px accent outline with 3px offset. Disabled buttons reduce opacity to 0.48 and use a not-allowed cursor. Background, text and border transitions take 160ms; there is no entrance choreography.

### Chips
Quiet status annotations. Neutral tags use secondary surface and muted text; positive tags use success roles. Example selectors and connection-mode tabs are 44px-high buttons with selected bottom rules, distinct from compact status tags.

### Cards / Containers
Outlined panels use surface, structural border and panel corners without permanent shadows. Typical padding is 20px or 24px; panel headings use 16px 20px. Footers may use secondary surface. Schema stays a ruled column; candidate and history lists stay ruled rows.

### Inputs / Fields
Native controls use surface, control-border, control corners and 10px 12px padding. Placeholders use muted at full opacity; disabled fields use 0.6 opacity. Textareas resize vertically. Query and question editors remove their field border inside an outlined panel; their focus outline moves inward.

Theme is a labelled native System / Light / Dark select with a Lucide state icon. Closed selects and option menus follow color-scheme. Preference follows the system until an override is chosen, persists locally and observes system changes; a same-origin head script resolves it before initial rendering.

### Navigation
The rail uses muted Sans labels and Lucide outline icons. Active destinations use selected wash, accent and medium weight; hover uses secondary surface and ink. Mobile menu exposes the rail below the top bar. Skip navigation becomes visible on focus. Preserve the original otter separately from interface icons.

### Evidence and Schema
Numbered question/review sequences, schema labels and tabular evidence are recurring signatures. Benchmarks keep baseline/candidate, variability and correctness scope together. Results preserve NULL/missing labels, bounded-snapshot context and grouped pagination. Empty states explain a next action; busy work names the operation and provides cancellation when available.

Schema uses native table and metadata disclosures. Its narrow-screen parent disclosure exposes fields without horizontal compression. Loading uses the existing one-second linear rotation only while busy. Reduced-motion rules disable animations and transitions and restore automatic scrolling. These controls require no animation library.

## Do's and Don'ts

### Do:
- **Do** preserve the exact original otter artwork and colors in both themes.
- **Do** use semantic theme roles and distinguish control boundaries from structural dividers.
- **Do** keep review, execution and measured scope visually explicit.
- **Do** preserve visible keyboard focus, native labels and reduced-motion behavior.
- **Do** use mobile schema disclosure and local table scrolling to retain readable work surfaces.
- **Do** keep numeric evidence aligned and explanations within bounded prose.

### Don't:
- **Don't** recolor, redraw or replace the original mascot.
- **Don't** invert the light palette to create dark mode.
- **Don't** introduce ornamental entrance animation or an animation dependency for native control states.
- **Don't** turn illustrative SQL or a scoped benchmark into fabricated universal evidence.
- **Don't** use decorative metric tiles, physical-material imitation or river puns as substitutes for useful context.
