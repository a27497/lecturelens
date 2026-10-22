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
    expect(video.play).not.toHaveBeenCalled();
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

it("reports bounded positions and forces the final seek coordinate", async () => {
  const wrapper = mount(VideoPlaybackCard, { props: { title: "video", description: "", playbackUrl: "/media", loading: false, errorMessage: "" } });
  const video = wrapper.get("video").element as HTMLVideoElement;
  video.currentTime = 1.234; await wrapper.get("video").trigger("timeupdate");
  video.currentTime = 1.3; await wrapper.get("video").trigger("timeupdate");
  expect(wrapper.emitted("position")).toEqual([[1234]]);
  video.currentTime = 4.567; await wrapper.get("video").trigger("seeked");
  expect(wrapper.emitted("position")!.at(-1)).toEqual([4567]);
  wrapper.unmount();
});
it("clamps restoration to media duration without autoplay", async () => {
  const wrapper = mount(VideoPlaybackCard, { props: { title: "video", description: "", playbackUrl: "/media", loading: false, errorMessage: "", seekRequest: { milliseconds: 100000, sequence: 1 } } });
  const video = wrapper.get("video").element as HTMLVideoElement;
  Object.defineProperty(video, "duration", { value: 12 });
  const play = vi.spyOn(video, "play");
  await wrapper.get("video").trigger("loadedmetadata");
  expect(video.currentTime).toBe(12); expect(play).not.toHaveBeenCalled();
  expect(wrapper.emitted("position")).toEqual([[12000]]);
  wrapper.unmount();
});
it("retains the position through token refresh and respects paused intent", async () => {
  const wrapper = mount(VideoPlaybackCard, { props: { title: "video", description: "", playbackUrl: "/old", loading: false, errorMessage: "" } });
  const old = wrapper.get("video").element as HTMLVideoElement;
  Object.defineProperty(old, "paused", { value: true });
  old.currentTime = 8; await wrapper.get("video").trigger("seeked");
  await wrapper.setProps({ playbackUrl: "", loading: true });
  await wrapper.setProps({ playbackUrl: "/new", loading: false });
  const video = wrapper.get("video").element as HTMLVideoElement;
  const play = vi.spyOn(video, "play");
  await wrapper.get("video").trigger("loadedmetadata");
  expect(video.currentTime).toBe(8); expect(play).not.toHaveBeenCalled();
  wrapper.unmount();
});
it("keeps the latest pending seek and ignores detached metadata positions", async () => {
  const wrapper = mount(VideoPlaybackCard, { props: { title: "video", description: "", playbackUrl: "", loading: true, errorMessage: "" } });
  wrapper.vm.seekTo(2); wrapper.vm.seekTo(9);
  await wrapper.setProps({ playbackUrl: "/media", loading: false });
  await wrapper.get("video").trigger("timeupdate");
  expect(wrapper.emitted("position")).toBeUndefined();
  await wrapper.get("video").trigger("loadedmetadata");
  expect((wrapper.get("video").element as HTMLVideoElement).currentTime).toBe(9);
  expect(wrapper.emitted("position")).toEqual([[9000]]);
  wrapper.unmount();
});

it("reports manual media seeks without treating playback or programmed seeks as intent", async () => {
  const wrapper = mount(VideoPlaybackCard, { props: { title: "video", description: "", playbackUrl: "/media", loading: false, errorMessage: "" } });
  const video = wrapper.get("video");
  await video.trigger("timeupdate");
  wrapper.vm.seekTo(2);
  await video.trigger("loadedmetadata"); await video.trigger("seeking"); await video.trigger("seeked");
  expect(wrapper.emitted("manualSeek")).toBeUndefined();
  (video.element as HTMLVideoElement).currentTime = 7;
  await video.trigger("seeking");
  expect(wrapper.emitted("manualSeek")).toHaveLength(1);
  wrapper.unmount();
});
