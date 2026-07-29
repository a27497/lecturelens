import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import VideoPlaybackCard from "./VideoPlaybackCard.vue";

describe("VideoPlaybackCard pending seek", () => {
  it("applies a seek requested before the player metadata is ready", async () => {
    const wrapper = mount(VideoPlaybackCard, {
      props: {
        title: "课程视频",
        description: "测试视频",
        playbackUrl: "",
        loading: true,
        errorMessage: "",
      },
    });

    wrapper.vm.seekTo(42);
    await wrapper.setProps({ playbackUrl: "/video.mp4", loading: false });
    const video = wrapper.get("video").element as HTMLVideoElement;
    vi.spyOn(video, "play").mockResolvedValue(undefined);

    await wrapper.get("video").trigger("loadedmetadata");

    expect(video.currentTime).toBe(42);
    expect(video.play).toHaveBeenCalledOnce();
  });
});
