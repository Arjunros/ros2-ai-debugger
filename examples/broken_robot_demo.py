#!/usr/bin/env python3
"""A deliberately broken fake robot for trying out ros2-ai-debugger.

Run in one terminal (with ROS 2 sourced):

    python3 examples/broken_robot_demo.py

then, in another:

    ros2 ai diagnose --no-ai

What is broken (on purpose):
  * /arm_controller and /controller_manager run, but nothing publishes /joint_states
    (robot_state_publisher is waiting for it).
  * TF has two disconnected trees (base_link.. and camera_link..).
  * /scan: BEST_EFFORT publisher vs RELIABLE subscriber (QoS mismatch).
  * /lifecycle_demo is stuck in the 'unconfigured' lifecycle state.
  * /imu_driver has a publisher on /imu/data but never publishes ("sensor not connected").
  * An action client waits for a server that does not exist.
  * /arm_controller logs an error periodically.

It only publishes fake data; it does not touch any hardware.
"""
import rclpy
from controller_manager_msgs.msg import ControllerState
from controller_manager_msgs.srv import ListControllers
from example_interfaces.action import Fibonacci
from geometry_msgs.msg import TransformStamped
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.lifecycle import Node as LifecycleNode
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu, JointState, LaserScan
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage


def tf(parent, child, stamp):
    t = TransformStamped()
    t.header.stamp = stamp
    t.header.frame_id, t.child_frame_id = parent, child
    t.transform.rotation.w = 1.0
    return t


def main():
    rclpy.init()
    arm = Node("arm_controller")
    arm.create_subscription(String, "/arm_controller/joint_trajectory", lambda m: None, 10)
    arm.create_timer(1.0, lambda: arm.get_logger().error("Failed to read joint states from hardware"))

    cm = Node("controller_manager")

    def list_controllers(_req, resp):
        c = ControllerState(name="arm_controller", state="active",
                            type="joint_trajectory_controller/JointTrajectoryController")
        resp.controller = [c]
        return resp

    cm.create_service(ListControllers, "/controller_manager/list_controllers", list_controllers)

    rsp = Node("robot_state_publisher")
    rsp.create_subscription(JointState, "/joint_states", lambda m: None, 10)
    tf_pub = rsp.create_publisher(TFMessage, "/tf", 10)
    static_pub = rsp.create_publisher(
        TFMessage, "/tf_static",
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    static_pub.publish(TFMessage(transforms=[tf("camera_link", "camera_optical_frame",
                                                rsp.get_clock().now().to_msg())]))
    rsp.create_timer(0.1, lambda: tf_pub.publish(TFMessage(transforms=[
        tf("base_link", "arm_link1", rsp.get_clock().now().to_msg())])))

    lidar = Node("lidar")
    scan_pub = lidar.create_publisher(LaserScan, "/scan", QoSProfile(
        depth=5, reliability=ReliabilityPolicy.BEST_EFFORT))
    lidar.create_timer(0.5, lambda: scan_pub.publish(LaserScan()))
    mapper = Node("mapper")
    mapper.create_subscription(LaserScan, "/scan", lambda m: None, QoSProfile(
        depth=5, reliability=ReliabilityPolicy.RELIABLE))

    lc = LifecycleNode("lifecycle_demo")  # never configured
    planner = Node("planner")
    ActionClient(planner, Fibonacci, "/compute_path")  # no server anywhere

    imu = Node("imu_driver")
    imu.create_publisher(Imu, "/imu/data", 10)  # created, but nothing is ever published
    imu.create_timer(1.0, lambda: imu.get_logger().warn("Could not open /dev/ttyUSB1: no such device"))

    ex = MultiThreadedExecutor()
    nodes = [arm, cm, rsp, lidar, mapper, lc, planner, imu]
    for n in nodes:
        ex.add_node(n)
    print("broken robot running; Ctrl+C to stop")
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    for n in nodes:
        n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
