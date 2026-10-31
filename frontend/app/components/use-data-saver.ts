"use client";

/**
 * Data saver: the low-bandwidth budget for the reader (installable row).
 *
 * Three inputs, one effective answer:
 *
 * - an explicit device-local override (`learny:data-saver` = "on" | "off"),
 *   set from the reading-controls popover — `off` deliberately beats the
 *   browser signal, so a learner on `Save-Data` who wants figures back wins;
 * - the platform signal, `navigator.connection.saveData` (Android Chrome's
 *   Data Saver), used when no override is stored;
 * - default off.
 *
 * The preference never reaches the server: it is a device concern, not an
 * account attribute, so there is no schema and no Account surface. While the
 * effective value is on, the reader does not request book figures and shows
 * its low-bandwidth notice; the service worker independently never caches
 * media responses, so data saver and offline caching cannot stack into a
 * large device-side cache.
 */

import { useCallback, useEffect, useState } from "react";

export const DATA_SAVER_KEY = "learny:data-saver";

/** The stored override, or null when the device has not chosen. */
export type DataSaverOverride = "on" | "off" | null;

/** A minimal storage shape so tests can pass fakes. */
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** Read the stored override; anything but "on"/"off" reads as unset. */
export function readDataSaverOverride(storage: StorageLike | null): DataSaverOverride {
  const value = storage?.getItem(DATA_SAVER_KEY);
  return value === "on" || value === "off" ? value : null;
}

/** The browser's own save-data signal, when the connection API exposes it. */
export function systemSaveData(
  connection: { saveData?: boolean } | null | undefined,
): boolean {
  return connection?.saveData === true;
}

/** The effective answer: an explicit choice wins, else the browser signal. */
export function resolveDataSaver(
  override: DataSaverOverride,
  saveData: boolean,
): boolean {
  if (override === "on") return true;
  if (override === "off") return false;
  return saveData;
}

/**
 * The reader's data-saver state: the effective value, the stored override, and
 * the setter that persists the choice device-local. The system signal is read
 * once on mount (it does not change mid-session), the override reacts live.
 */
export function useDataSaver(): {
  dataSaver: boolean;
  override: DataSaverOverride;
  system: boolean;
  setOverride: (value: "on" | "off" | null) => void;
} {
  const [override, setOverrideState] = useState<DataSaverOverride>(null);
  const [system, setSystem] = useState(false);

  useEffect(() => {
    setOverrideState(readDataSaverOverride(window.localStorage));
    const nav = navigator as Navigator & { connection?: { saveData?: boolean } };
    setSystem(systemSaveData(nav.connection));
  }, []);

  const setOverride = useCallback((value: "on" | "off" | null) => {
    setOverrideState(value);
    if (value === null) {
      window.localStorage.removeItem(DATA_SAVER_KEY);
    } else {
      window.localStorage.setItem(DATA_SAVER_KEY, value);
    }
  }, []);

  return { dataSaver: resolveDataSaver(override, system), override, system, setOverride };
}
