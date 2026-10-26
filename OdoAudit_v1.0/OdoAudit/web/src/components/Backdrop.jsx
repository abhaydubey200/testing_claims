import bg from "../assets/background.svg";

/** The chaicode.com page background: one SVG with a warm glow and faint
 *  hexagons, centred at the top, behind everything. First child of the page
 *  wrapper (which is `relative isolate overflow-x-clip`). */
export default function Backdrop() {
  return (
    <img
      src={bg}
      alt=""
      aria-hidden="true"
      className="chai-backdrop"
      fetchPriority="high"
      decoding="async"
    />
  );
}
