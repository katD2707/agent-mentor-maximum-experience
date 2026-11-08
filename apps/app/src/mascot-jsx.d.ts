// The package's own JSX augmentation can't resolve "react" from packages/mentor-mascot, so declare it here.
import type { MentorMascot, MentorMascotAttributes } from "@mentor/mentor-mascot/mascot";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "mentor-mascot": React.DetailedHTMLProps<React.HTMLAttributes<MentorMascot>, MentorMascot> & MentorMascotAttributes;
    }
  }
}
