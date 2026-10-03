# Dashboard design and review

Hallmark was applied to the visual layer of the existing Streamlit choice.
The proposal supplies the pricing and operations audience and the scenario
comparison use case. The inferred tone is restrained and technical.

- **Macrostructure:** Workbench; functional headings and the actual tool as the content.
- **Theme:** Cobalt, with cool paper, restrained blue, local Bahnschrift display
  and Segoe UI body fonts. Streamlit's native theme configuration follows the tokens.
- **Enrichment:** None; charts use computed artifacts.
- **Sections:** Run/DGP/seed selector; Operations; Method checks; Price scenarios;
  exports and interpretation notes.
- **Motion:** Native widget feedback; no custom animation. Reduced motion supported.
- **Review:** Headless Edge checked all tabs, outside-support rejection and recovery,
  and 320/375/414/768 px layouts with no page overflow. Screenshots are ignored QA
  intermediates in `.cache/dashboard-qa-final/`. Final review used the TLC-context
  model `20261003T130951-df24a7e4`, including its 199-draw uncertainty display.

Portable visual values are in `tokens.css`; layout styling is in
`src/gsm_poc/ui.css`. Controls use Streamlit state, loading, errors and success
behavior. Focus rings are immediate. Source and uncertainty labels are adjacent
to outputs, and tables retain their local horizontal scroll at narrow widths.

The in-app browser Node runtime was not available; verification used the local
Playwright developer dependency and installed headless Edge. The browser check
does not train models or access external systems.
