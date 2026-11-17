// preset لـTailwind من هوية misk: الأدوار تقرأ متغيرات tokens.css (فاتح وداكن)، والتدرجات قيم ثابتة.
module.exports = {
  "theme": {
    "extend": {
      "colors": {
        "brand": {
          "50": "#FFF1F3",
          "100": "#FFDEE4",
          "200": "#F8C5CE",
          "300": "#E4A8B3",
          "400": "#CC8896",
          "500": "#B46A7A",
          "600": "#9B4C5F",
          "700": "#843248",
          "800": "#68112F",
          "900": "#510020",
          "950": "#350012"
        },
        "accent": {
          "50": "#FFF3E4",
          "100": "#FFE3BF",
          "200": "#EECFA5",
          "300": "#D6B68C",
          "400": "#B79972",
          "500": "#997E5B",
          "600": "#7C6546",
          "700": "#624F35",
          "800": "#4A3A24",
          "900": "#332615",
          "950": "#201609"
        },
        "neutral": {
          "50": "#FDF2F5",
          "100": "#F0E4E8",
          "200": "#DDD0D4",
          "300": "#C4B6BA",
          "400": "#A99A9E",
          "500": "#8E7E83",
          "600": "#6C5C61",
          "700": "#5D4E53",
          "800": "#46393D",
          "900": "#312529",
          "950": "#1F1518"
        },
        "success": {
          "50": "#E3FCEF",
          "100": "#D4F0E1",
          "200": "#BEDDCC",
          "300": "#A2C4B2",
          "400": "#83A995",
          "500": "#658E79",
          "600": "#3E6954",
          "700": "#335D49",
          "800": "#1F4634",
          "900": "#0B3121",
          "950": "#001F12"
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
          "IBM Plex Sans Arabic",
          "Tahoma",
          "sans-serif"
        ],
        "body": [
          "IBM Plex Sans Arabic",
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
