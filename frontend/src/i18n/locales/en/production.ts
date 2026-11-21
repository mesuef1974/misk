import type ar from "../ar/production";

const production: typeof ar = {
  title: "Production",
  sheetStatus: {
    planned: "Planned",
    done: "Done",
    scrapped: "Scrapped",
  },
  outcome: {
    ok: "Succeeded",
    failed: "Failed",
  },
  duration: {
    seconds: "{seconds} s",
    minutes: "{minutes} min",
    both: "{minutes} min {seconds} s",
  },
  material: {
    named: "{name} ({thickness} mm)",
    unknown: "Material {id}",
  },
  plan: {
    label: "Plan new sheets for a material",
    choose: "Choose a material",
    busy: "Planning…",
    submit: "Plan sheets",
    planned: "Planned {pieces} pieces on {sheets} sheets.",
    alreadyPlanned: "Nothing new to plan: this material's pieces are already planned on {waiting} sheets waiting to be cut.",
    nothing: "No pieces are waiting to be planned for this material. Only items of confirmed and in-production orders are planned.",
    timeout: "Planning is taking longer than usual. Refresh the page shortly to see the sheets.",
  },
  filter: {
    label: "Filter by status",
    all: "All",
  },
  list: {
    retry: "Try again",
    loading: "Loading sheets…",
    empty: "No sheets yet. Confirm an order, then plan sheets for its material above.",
    noneInStatus: "No sheets with this status.",
    showing: "Showing {shown} of {total}",
    loadingMore: "Loading…",
    loadMore: "Load more",
  },
  sheet: {
    title: "Sheet {id}",
    usage: "{pieces} pieces · {used} used",
    diagram: "Sheet {id}: {pieces} pieces on {width} × {height} mm",
    groupTitle: "{template} — {customer}",
    order: "Order {id}",
    runsLabel: "Run log for sheet {id}",
    runs: "Run log",
    materialCost: "Material cost {cost}",
    recordRun: "Record a run",
    scrapWarning: "The sheet's pieces are released to be planned on a new sheet. This cannot be undone.",
    confirmScrap: "Confirm scrapping",
    cancelScrap: "Go back",
    scrap: "Scrap sheet",
  },
  run: {
    title: "Record a run for sheet {id}",
    minutes: "Duration: minutes",
    seconds: "Seconds",
    outcome: "Outcome",
    calibration: "Calibration used (optional)",
    noCalibration: "No calibration",
    calibrationOption: "{operation} · {power}% · {speed} mm/s · {date}",
    calibrationsFailed: "Could not load calibrations: {reason}",
    notes: "Notes (optional)",
    hint: "A successful run closes the sheet for good. A failed run keeps it planned for another run.",
    saving: "Saving…",
    save: "Save run",
    cancel: "Cancel",
    errors: {
      durationRange: "Whole minutes, and seconds between 0 and 59",
      durationRequired: "Run duration is required",
      outcome: "Choose the outcome",
    },
  },
};

export default production;
