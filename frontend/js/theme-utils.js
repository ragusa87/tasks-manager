// Pure helpers of the theme toggle (theme.js). DOM-free for node testing.

// Cycle order of the toggle: follow the OS, then pin light, then pin dark.
export const THEME_CYCLE = ['system', 'light', 'dark'];

export function nextTheme(current) {
    const index = THEME_CYCLE.indexOf(current);
    return THEME_CYCLE[(index + 1) % THEME_CYCLE.length];
}

export function themeLabel(theme) {
    return theme === 'system' ? 'Theme: follows system' : 'Theme: ' + theme;
}
