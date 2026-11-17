// preset لـTailwind من هوية misk: الأدوار تقرأ متغيرات tokens.css (فاتح وداكن)، والتدرجات قيم ثابتة.
module.exports = {
  "theme": {
    "extend": {
      "colors": {
        "brand": {
          "50": "#E6FAF5",
          "100": "#D7EEE7",
          "200": "#C1DBD4",
          "300": "#A4C2BA",
          "400": "#84A79E",
          "500": "#668D83",
          "600": "#487368",
          "700": "#2F5C52",
          "800": "#1E4D43",
          "900": "#013128",
          "950": "#001E18"
        },
        "accent": {
          "50": "#FFF2ED",
          "100": "#FFE0D5",
          "200": "#FFC5AF",
          "300": "#F0A689",
          "400": "#D5896B",
          "500": "#C4785A",
          "600": "#97543A",
          "700": "#7B4028",
          "800": "#602C17",
          "900": "#451A07",
          "950": "#2F0B00"
        },
        "neutral": {
          "50": "#F1F7F4",
          "100": "#E3EAE7",
          "200": "#CFD6D3",
          "300": "#B5BDB9",
          "400": "#98A19D",
          "500": "#7D8682",
          "600": "#5E6763",
          "700": "#4C5551",
          "800": "#383F3C",
          "900": "#242B28",
          "950": "#141A17"
        },
        "success": {
          "50": "#E1FFDF",
          "100": "#CBF6C8",
          "200": "#B4E3B2",
          "300": "#97CA94",
          "400": "#77AF74",
          "500": "#589456",
          "600": "#3B7A3A",
          "700": "#256225",
          "800": "#104A12",
          "900": "#003303",
          "950": "#002001"
        },
        "warning": {
          "50": "#FFF3E6",
          "100": "#FFE3C3",
          "200": "#F3CDA2",
          "300": "#DCB282",
          "400": "#C2955F",
          "500": "#A8783D",
          "600": "#8A5A14",
          "700": "#734800",
          "800": "#563500",
          "900": "#3B2300",
          "950": "#251400"
        },
        "error": {
          "50": "#FFF1F1",
          "100": "#FFDFDE",
          "200": "#FFC3C1",
          "300": "#FF9A99",
          "400": "#E87879",
          "500": "#CE575C",
          "600": "#B0363F",
          "700": "#941F2C",
          "800": "#76021A",
          "900": "#53000F",
          "950": "#360006"
        },
        "info": {
          "50": "#ECF7FF",
          "100": "#D3ECFF",
          "200": "#B5DAF5",
          "300": "#97C0DF",
          "400": "#77A5C6",
          "500": "#5889AC",
          "600": "#3A6F93",
          "700": "#2D6387",
          "800": "#0B4161",
          "900": "#002C45",
          "950": "#001A2C"
        },
        "misk": {
          "bg": "var(--misk-bg)",
          "surface": "var(--misk-surface)",
          "raised": "var(--misk-raised)",
          "border": "var(--misk-border)",
          "text": "var(--misk-text)",
          "text-muted": "var(--misk-text-muted)",
          "brand": "var(--misk-brand)",
          "brand-strong": "var(--misk-brand-strong)",
          "on-brand": "var(--misk-on-brand)",
          "accent": "var(--misk-accent)",
          "border-strong": "var(--misk-border-strong)",
          "focus": "var(--misk-focus)",
          "brand-soft": "var(--misk-brand-soft)",
          "accent-text": "var(--misk-accent-text)",
          "accent-soft": "var(--misk-accent-soft)",
          "success": "var(--misk-success)",
          "warning": "var(--misk-warning)",
          "error": "var(--misk-error)",
          "info": "var(--misk-info)",
          "success-soft": "var(--misk-success-soft)",
          "warning-soft": "var(--misk-warning-soft)",
          "error-soft": "var(--misk-error-soft)",
          "info-soft": "var(--misk-info-soft)"
        }
      },
      "fontFamily": {
        "heading": [
          "Cairo",
          "Tahoma",
          "sans-serif"
        ],
        "body": [
          "Almarai",
          "Tahoma",
          "sans-serif"
        ]
      },
      "fontSize": {
        "caption": [
          "0.75rem",
          {
            "lineHeight": "1.7"
          }
        ],
        "small": [
          "0.8rem",
          {
            "lineHeight": "1.7"
          }
        ],
        "body": [
          "1.0rem",
          {
            "lineHeight": "1.7"
          }
        ],
        "lead": [
          "1.25rem",
          {
            "lineHeight": "1.7"
          }
        ],
        "h4": [
          "1.5625rem",
          {
            "lineHeight": "1.3"
          }
        ],
        "h3": [
          "1.95rem",
          {
            "lineHeight": "1.3"
          }
        ],
        "h2": [
          "2.4438rem",
          {
            "lineHeight": "1.3"
          }
        ],
        "h1": [
          "3.05rem",
          {
            "lineHeight": "1.3"
          }
        ],
        "display": [
          "3.8125rem",
          {
            "lineHeight": "1.3"
          }
        ]
      }
    }
  }
};
