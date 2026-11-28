// Match the backend's narrow exception for numeric ASPX product IDs.
export function validExactManufacturerUrl(value: string): boolean {
  if (!/^https:\/\/[^/]+\/[^?#]+(?:\?id=[1-9][0-9]{0,9})?$/.test(value) ||
      /[%\\\s#]/.test(value) || /[^\x21-\x7e]/.test(value)) return false;
  try {
    const url = new URL(value);
    if (url.username || url.password || url.port || !url.hostname ||
        !/^[a-z0-9.-]+$/i.test(url.hostname) || url.hostname.includes("..") ||
        /^\d+$/.test(url.hostname.replace(/\./g, ""))) return false;
    if (value.includes("?")) {
      return /\.aspx$/i.test(url.pathname) &&
        /^\?id=[1-9][0-9]{0,9}$/.test(url.search) &&
        /^https:\/\/[^/:]+\//.test(value);
    }
    return true;
  } catch {
    return false;
  }
}

