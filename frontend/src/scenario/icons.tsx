const PATHS = {
  logo: 'M12 3 3 7.5 12 12l9-4.5L12 3ZM3 12l9 4.5 9-4.5M3 16.5 12 21l9-4.5',
  home: 'M3 11 12 3l9 8M5 9.5V21h5v-6h4v6h5V9.5',
  upload: 'M6 3h9l4 4v14H6V3ZM14 3v5h5M9 13h7M9 17h7',
  shield: 'M12 3 4 6v6c0 5 3.5 8 8 9 4.500-1 8-4 8-9V6l-8-3ZM8.500 12l2.500 2.500 4.500-5',
  chart: 'M3 3v18h18M7 15l4-5 4 3 5-7',
  calendar: 'M4 5h16v16H4V5ZM4 10h16M8 3v4M16 3v4M8 14h2M14 14h2M8 17.500h2',
  box: 'M12 3 4 7v10l8 4 8-4V7l-8-4ZM4 7l8 4 8-4M12 11v10',
  bell: 'M6 17V11a6 6 0 0 1 12 0v6l2 2H4l2-2ZM10 21h4',
  help: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM9.500 9.500a2.500 2.500 0 1 1 3.500 2.300c-.700.400-1 .900-1 1.700M12 17h.01',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21c1-4 4-6 8-6s7 2 8 6',
  check: 'M5 12.500l4.500 4.500L19 7.500',
  checkCircle: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM8 12.500l2.800 2.800L16 9.500',
  warn: 'M12 3 2 20h20L12 3ZM12 10v4.500M12 17.500h.01',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v6M12 7.500h.01',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  arrowLeft: 'M19 12H5M11 6l-6 6 6 6',
  chevronRight: 'M9 5l7 7-7 7',
  plus: 'M12 5v14M5 12h14',
  eye: 'M2 12s3.500-7 10-7 10 7 10 7-3.500 7-10 7S2 12 2 12ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  edit: 'M4 20h4L19 9l-4-4L4 16v4ZM13.500 6.500l4 4',
  refresh: 'M20 11a8 8 0 0 0-14.500-4M4 4v4h4M4 13a8 8 0 0 0 14.500 4M20 20v-4h-4',
  download: 'M12 4v11M7 10.500l5 5 5-5M4 20h16',
  play: 'M7 4.500v15l12-7.500-12-7.500Z',
  file: 'M6 3h9l4 4v14H6V3ZM14 3v5h5',
  db: 'M4 6c0-1.700 3.600-3 8-3s8 1.300 8 3-3.600 3-8 3-8-1.300-8-3ZM4 6v6c0 1.700 3.600 3 8 3s8-1.300 8-3V6M4 12v6c0 1.700 3.600 3 8 3s8-1.300 8-3v-6',
  bars: 'M4 20V11h4v9M10 20V5h4v15M16 20v-7h4v7M3 20h18',
  sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 4.500v5M9 14.500v5',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM16 16l4.500 4.500',
  save: 'M5 4h11l3 3v13H5V4ZM8 4v5h7V4M8 20v-6h8v6',
  link: 'M10 14a4 4 0 0 0 5.700 0l3-3a4 4 0 0 0-5.700-5.700l-1 1M14 10a4 4 0 0 0-5.700 0l-3 3a4 4 0 0 0 5.700 5.700l1-1',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3.500 2',
  gear: 'M12 15.500a3.500 3.500 0 1 0 0-7 3.500 3.500 0 0 0 0 7ZM12 2.500v3M12 18.500v3M2.500 12h3M18.500 12h3M5.300 5.300l2.100 2.100M16.600 16.600l2.100 2.100M5.300 18.700l2.100-2.100M16.600 7.400l2.100-2.100',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM12 12h.01',
  tag: 'M3 12V4h8l10 10-8 8L3 12ZM7.500 8.500h.01',
  external: 'M14 4h6v6M20 4l-9 9M18 14v6H4V6h6',
  ban: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM5.700 5.700l12.600 12.600',
  scale: 'M12 4v16M6 20h12M5 8h14M5 8l-3 6a3 3 0 0 0 6 0L5 8ZM19 8l-3 6a3 3 0 0 0 6 0l-3-6Z',
} as const;

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 18, fill = false }: { name: IconName; size?: number; fill?: boolean }) {
  return <svg className="sc-icon" width={size} height={size} viewBox="0 0 24 24" fill={fill ? 'currentColor' : 'none'}
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <path d={PATHS[name]} />
  </svg>;
}
