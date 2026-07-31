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

  it("uses the probed subtitle language and has no static codec warning", () => {
    const wrapper = mount(VideoPlaybackCard, {
      props: {
        title: "课程视频",
        description: "测试视频",
        playbackUrl: "/video.mp4",
        loading: false,
        errorMessage: "",
        subtitleTrackUrl: "/subtitle.vtt",
        subtitleLanguage: "en",
      },
    });

    expect(wrapper.get("track").attributes("srclang")).toBe("en");
    expect(wrapper.text()).not.toContain("当前浏览器可能不支持该视频编码");
  });

  it("shows codec guidance only for a real unsupported-source error and clears it on canplay", async () => {
    const wrapper = mount(VideoPlaybackCard, {
      props: {
        title: "课程视频",
        description: "测试视频",
        playbackUrl: "/video.mp4",
        loading: false,
        errorMessage: "",
      },
    });
    const video = wrapper.get("video").element as HTMLVideoElement;
    Object.defineProperty(video, "error", { configurable: true, value: { code: 4 } });

    await wrapper.get("video").trigger("error");
    expect(wrapper.get("el-alert").attributes("title")).toContain("浏览器不支持该视频编码或格式");

    await wrapper.get("video").trigger("canplay");
    expect(wrapper.find("el-alert").exists()).toBe(false);
  });
});
