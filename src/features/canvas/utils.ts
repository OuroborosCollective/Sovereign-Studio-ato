import { BoardState } from './types';

export const STORAGE_KEY = 'sovereign_canvas_tool_board_v1';

export const defaultBoard = (): BoardState => ({
  title: 'GitHub Auto-Fix Demo Workflow',
  blueprint: 'Demo Workflow Canvas',
  cards: [],
  updatedAt: new Date().toISOString(),
});
