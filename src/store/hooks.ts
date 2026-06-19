import {
  shallowEqual,
  useDispatch,
  useSelector,
  type TypedUseSelectorHook,
} from 'react-redux';

import type { AppDispatch, RootState } from './index';

export type AppSelector<TSelected> = (state: RootState) => TSelected;

export type AppSelectorEquality<TSelected> = (
  left: TSelected,
  right: TSelected,
) => boolean;

export type NullableAppSelector<TSelected> = AppSelector<TSelected | null | undefined>;

export interface RequiredSelectorOptions {
  name?: string;
  message?: string;
}

export const appReferenceEqual: AppSelectorEquality<unknown> = Object.is;

export const appShallowEqual = shallowEqual as AppSelectorEquality<unknown>;

function selectorName(options?: RequiredSelectorOptions): string {
  return options?.name?.trim() || 'required Redux selector';
}

function missingSelectorMessage(options?: RequiredSelectorOptions): string {
  return (
    options?.message?.trim() ||
    `${selectorName(options)} returned null or undefined.`
  );
}

export function useAppDispatch(): AppDispatch {
  return useDispatch<AppDispatch>();
}

export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;

export function useAppSelectorWithEquality<TSelected>(
  selector: AppSelector<TSelected>,
  equalityFn: AppSelectorEquality<TSelected>,
): TSelected {
  return useSelector(selector, equalityFn);
}

export function useAppShallowSelector<TSelected>(
  selector: AppSelector<TSelected>,
): TSelected {
  return useSelector(selector, shallowEqual);
}

export function useRequiredAppSelector<TSelected>(
  selector: NullableAppSelector<TSelected>,
  options?: RequiredSelectorOptions,
): TSelected {
  const selected = useSelector(selector);

  if (selected === null || selected === undefined) {
    throw new Error(missingSelectorMessage(options));
  }

  return selected;
}

export function useRequiredAppShallowSelector<TSelected>(
  selector: NullableAppSelector<TSelected>,
  options?: RequiredSelectorOptions,
): TSelected {
  const selected = useSelector(selector, shallowEqual);

  if (selected === null || selected === undefined) {
    throw new Error(missingSelectorMessage(options));
  }

  return selected;
}

export function useAppBooleanSelector(selector: AppSelector<boolean>): boolean {
  return useSelector(selector);
}

export function useAppNumberSelector(selector: AppSelector<number>): number {
  return useSelector(selector);
}

export function useAppStringSelector(selector: AppSelector<string>): string {
  return useSelector(selector);
}
