import type { Messages } from "@/i18n";
import catalog from "./en/catalog";
import orders from "./en/orders";
import production from "./en/production";
import store from "./en/store";

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
    about: "About us",
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
  store,
  about: {
    heading: "About us",
    lead: "Misk Design is a laser engraving workshop in Qatar: your name is drawn, then engraved on leather, wood and acrylic.",
    steps: {
      design: {
        title: "You see it before you pay.",
        body: "The preview on the product page is the engraving file itself, in the font and size that leave the workshop.",
      },
      make: {
        title: "We engrave to order.",
        body: "Every piece is made for its owner after payment, and its ready date is calculated from the workshop's actual queue.",
      },
      receive: {
        title: "You follow your order.",
        body: "A private tracking link shows the order's stage, and you book your pickup slot from it.",
      },
    },
    audit: "What you confirm in the preview is what we engrave, and we let the natural material show its colour and texture.",
  },
  notFound: {
    heading: "Page not found",
    body: "There is no page at this address. The link may be old or mistyped.",
    home: "Home page",
  },
};

export default en;
