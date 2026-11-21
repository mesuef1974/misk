import type { Messages } from "@/i18n";
import catalog from "./en/catalog";
import orders from "./en/orders";
import production from "./en/production";

const en: Messages = {
  site: {
    slogan: "Your name, drawn then engraved",
  },
  language: {
    switchTo: "العربية",
    switchLabel: "التحويل إلى العربية",
  },
  nav: {
    sections: "Platform sections",
    account: "Account and settings",
    orders: "Orders",
    production: "Production",
    materials: "Materials",
    templates: "Templates",
    about: "About",
    admin: "Admin panel",
    login: "Sign in",
    logout: "Sign out",
    logoutFailed: "Could not sign out: {reason}",
  },
  status: {
    checking: "Checking the server…",
    up: "Server is running",
    down: "Server is not responding",
  },
  home: {
    heading: "Your name, drawn then engraved.",
    lead: "Order management for a laser workshop: the catalog, orders, and sheet planning and runs.",
    staffLogin: "Staff sign-in",
    traits: {
      precise: {
        title: "Precise",
        body: "We check the spelling of every name with its owner before engraving, and state the size, material, quantity and pickup time in numbers.",
      },
      warm: {
        title: "Warm",
        body: "We ask about the occasion and who it is for before we suggest anything, and let the natural material show its own color and texture.",
      },
      elegant: {
        title: "Elegant",
        body: "We choose one typeface that suits the name, leave space around it, and say what is needed in a short sentence.",
      },
    },
  },
  dashboard: {
    newOrder: "New order",
    retry: "Try again",
    openOrders: "Open orders",
    workshop: "Workshop",
    plannedSheets: "Sheets waiting to run",
    materials: "Materials",
    templates: "Templates",
  },
  errors: {
    network: "Could not connect. Check the network and try again",
    unauthorized: "Sign in with a staff account",
    forbidden: "You do not have permission for this action",
    notFound: "Not found",
    tooMany: "Too many attempts; try again shortly",
    failed: "The operation could not be completed ({status})",
    unexpected: "An unexpected error occurred",
  },
  currency: "QAR",
  orderStatus: {
    draft: "Draft",
    awaiting_payment: "Awaiting payment",
    paid: "Paid",
    under_review: "Under review",
    confirmed: "Confirmed",
    in_production: "In production",
    ready: "Ready",
    out_for_delivery: "Out for delivery",
    ready_for_pickup: "Ready for pickup",
    delivered: "Delivered",
    cancelled: "Cancelled",
    refunded: "Refunded",
  },
  orderAction: {
    under_review: "Send for review",
    confirmed: "Confirm order",
    in_production: "Start production",
    ready: "Mark ready",
    out_for_delivery: "Out for delivery",
    ready_for_pickup: "Ready for pickup",
    delivered: "Hand over to customer",
    cancelled: "Cancel order",
  },
  login: {
    heading: "Sign in",
    username: "Username",
    passLabel: "Password",
    checking: "Checking…",
    submit: "Sign in",
  },
  theme: {
    button: "Appearance",
    buttonLabel: "Appearance: {palette} palette, {mode} mode. Press to change",
    dialog: "Platform appearance",
    palette: "Palette",
    mode: "Mode",
    hint: "Every palette has its own day and night.",
    modes: { auto: "Auto", light: "Day", dark: "Night" },
    palettes: {
      navy: "Navy",
      "royal-blue": "Royal blue",
      teal: "Teal",
      emerald: "Emerald",
      olive: "Olive",
      purple: "Purple",
      rose: "Rose",
      chocolate: "Chocolate",
      black: "Black",
      oud: "Oud",
    },
  },
  orders,
  production,
  catalog,
  about: {
    heading: "About",
    lead: "Misk runs the work of a small laser workshop, from the order to the finished piece.",
    steps: {
      catalog: {
        title: "Catalog.",
        body: "Materials with their thicknesses and sheet costs, a calibration for each material from a test offcut, and product templates with the fields an order fills in.",
      },
      orders: {
        title: "Orders.",
        body: "An order is saved as a draft, then confirmed, and it cannot be confirmed before every material in it is calibrated.",
      },
      production: {
        title: "Production.",
        body: "Pieces from confirmed orders are laid out on sheets of the material, then each sheet run is recorded with its duration, result and material cost.",
      },
    },
    audit: "Every write is recorded in the audit log, and sign-in is for staff accounts only.",
  },
  notFound: {
    heading: "Page not found",
    body: "There is no page at this address. The link may be old or mistyped.",
    home: "Home page",
  },
};

export default en;
