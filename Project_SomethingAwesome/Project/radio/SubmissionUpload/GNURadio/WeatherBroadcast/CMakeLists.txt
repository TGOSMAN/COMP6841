cmake_minimum_required(VERSION 4.2)
project(WeatherBroadcast C)

set(CMAKE_C_STANDARD 11)

include_directories(.)

add_executable(WeatherBroadcast
        MyEmbeddedAlarmSystem.c
        MyEmbeddedAlarmSystem.h)

