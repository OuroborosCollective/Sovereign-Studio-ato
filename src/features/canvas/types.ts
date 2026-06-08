export interface BoardCard {
  id: string;
  title: string;
  body: string;
  x: number;
  y: number;
  color: 'amber' | 'indigo' | 'emerald' | 'rose' | 'sky';
}

export interface BoardState {
  title: string;
  blueprint: string;
  cards: BoardCard[];
  updatedAt: string;
}

export const COLORS: BoardCard['color'][] = ['amber', 'indigo', 'emerald', 'rose', 'sky'];
