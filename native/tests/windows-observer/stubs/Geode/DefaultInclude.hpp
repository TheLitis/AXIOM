#pragma once
#include <matjson.hpp>

namespace cocos2d {
struct CCEGLView {
    void* m_pMainWindow = nullptr;
    static CCEGLView* get();
};
}
namespace geode::prelude { using cocos2d::CCEGLView; }
namespace geode::utils { double getInputTimestamp(); }
